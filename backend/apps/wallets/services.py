"""Wallet connection, ownership verification, and claims (Spec 04).

Ownership of a wallet is proven by a signature over a server-issued nonce,
never by the address alone. Claims are idempotent and, once created, carry a
signed EIP-712 authorization the seller's wallet submits to the distributor
contract.
"""
import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from eth_account import Account
from eth_account.messages import encode_defunct

from apps.audit.models import AuditLog
from apps.rewards.exceptions import RewardEngineError
from apps.rewards.models import Reward, RewardStatus

from .models import Claim, ClaimStatus, Wallet

# Message sellers are asked to sign. The address and nonce make signature
# replies non-replayable and bound to a specific wallet. The frontend signs
# exactly the string returned by `wallet_nonce_message`.
NONCE_MESSAGE_TEMPLATE = (
    "CryptoSocialRewards: verify wallet ownership.\n"
    "Wallet: {address}\nChain: {chain_id}\nNonce: {nonce}"
)


def _normalize_address(address: str) -> str:
    return address.strip().lower()


def wallet_nonce_message(wallet) -> str:
    """The exact message a seller must sign to prove wallet ownership."""
    return NONCE_MESSAGE_TEMPLATE.format(
        address=wallet.address, chain_id=wallet.chain_id, nonce=wallet.nonce
    )


def create_or_get_wallet(seller, address, chain_id, *, actor=None) -> Wallet:
    """Create (or fetch) a wallet for the seller; generate a fresh nonce."""
    address = _normalize_address(address)
    wallet, _ = Wallet.objects.get_or_create(
        seller=seller,
        address=address,
        chain_id=chain_id,
        defaults={"network": "sepolia", "wallet_type": Wallet.WalletType.EVM},
    )
    wallet.nonce = secrets.token_hex(32)
    wallet.verified = False
    wallet.last_seen_at = timezone.now()
    wallet.save(update_fields=["nonce", "verified", "last_seen_at"])
    return wallet


def verify_wallet_signature(wallet, signature, *, actor=None) -> Wallet:
    """Verify the signature produced by the wallet over the nonce message.

    Uses dedicated signature recovery: only an address whose private key
    signed the nonce message can prove ownership. The nonce is one-time and is
    cleared on success, so a captured signature cannot be replayed.
    """
    address = _normalize_address(wallet.address)
    message = wallet_nonce_message(wallet)
    try:
        recovered = Account.recover_message(
            encode_defunct(text=message), signature=signature
        )
    except (ValueError, TypeError) as exc:
        raise RewardEngineError(f"Signature could not be verified: {exc}") from exc

    if _normalize_address(recovered) != address:
        raise RewardEngineError("Signature verification failed: signer does not match wallet.")

    wallet.verified = True
    wallet.nonce = ""  # one-time nonce; clear after successful verification
    wallet.last_seen_at = timezone.now()
    wallet.save(update_fields=["verified", "nonce", "last_seen_at"])
    AuditLog.objects.create(
        actor=actor,
        action="WALLET_VERIFIED",
        object_type="Wallet",
        object_id=str(wallet.pk),
        metadata={"address": wallet.address, "chain_id": wallet.chain_id},
    )
    return wallet


def create_claim(seller, wallet, reward, *, actor=None) -> Claim:
    """Create a claim authorization for an AVAILABLE reward.

    Idempotency: a seller can only have one open claim per reward (enforced by
    this check; the unique partial index protects the DB level too).
    Also enforces the emergency claiming pause and campaign-level disabling
    (Spec 04).
    """
    from apps.blockchain import services as chain  # noqa: PLC0415 - lazy: avoids an import cycle

    if chain.is_claiming_paused():
        raise RewardEngineError("Claiming is temporarily paused. Please retry later.")

    campaign = reward.campaign
    if campaign and campaign.status in ("PAUSED", "CANCELLED"):
        raise RewardEngineError(
            f"Claims for this campaign are disabled ({campaign.status})."
        )

    if wallet.seller_id != seller.id:
        raise RewardEngineError("Wallet does not belong to this seller.")
    if not wallet.verified:
        raise RewardEngineError("Wallet ownership is not verified.")
    if reward.status != RewardStatus.AVAILABLE:
        raise RewardEngineError(f"Reward is {reward.status}, not AVAILABLE.")

    with transaction.atomic():
        reward_locked = Reward.objects.select_for_update().get(pk=reward.pk)
        if reward_locked.status != RewardStatus.AVAILABLE:
            raise RewardEngineError(f"Reward is {reward_locked.status}, not AVAILABLE.")

        existing_open = Claim.objects.filter(reward=reward).exclude(
            status__in=[ClaimStatus.FAILED, ClaimStatus.EXPIRED]
        )
        if existing_open.exists():
            raise RewardEngineError("A claim for this reward already exists.")

        # Token decimals come from the allowlist when present, else a default.
        token = chain.get_token_config_or_none(reward_locked.chain_id, reward_locked.token_symbol)
        decimals = token.decimals if token else chain.default_token_decimals()
        amount_smallest = chain.signing.reward_amount_smallest(reward_locked.amount, decimals)

        claim = Claim.objects.create(
            seller=seller,
            wallet=wallet,
            reward=reward_locked,
            amount=reward_locked.amount,
            amount_smallest_unit=amount_smallest,
            token_symbol=reward_locked.token_symbol,
            chain_id=reward_locked.chain_id,
            status=ClaimStatus.CREATED,
            nonce=secrets.token_hex(32),
            expired_at=timezone.now() + timedelta(hours=24),
        )

        # Attach the signed authorization when the signer is configured. If it
        # is not (or the chain is not enabled yet), the seller can still receive
        # it later via the authorization endpoint — the claim itself is valid.
        try:
            chain.get_claim_authorization_payload(claim)
        except chain.BlockchainError:
            pass

        from apps.blockchain.ledger import record  # noqa: PLC0415 - lazy: avoids an import cycle
        from apps.blockchain.models import LedgerAction  # noqa: PLC0415 - lazy import

        record(
            LedgerAction.CLAIM_CREATED,
            seller=seller,
            reward=reward_locked,
            claim=claim,
            wallet=wallet,
            amount=claim.amount,
        )
        AuditLog.objects.create(
            actor=actor,
            action="CLAIM_CREATED",
            object_type="Claim",
            object_id=str(claim.pk),
            metadata={
                "wallet": wallet.address,
                "amount": str(claim.amount),
                "reward_id": reward_locked.pk,
            },
        )
    return claim


def claim_authorization_available(claim) -> bool:
    """Whether a signed authorization is meaningful for this claim state."""
    return claim.status in (
        ClaimStatus.CREATED,
        ClaimStatus.SIGNING,
        ClaimStatus.SUBMITTED,
        ClaimStatus.PENDING,
    )


def claim_to_dict(claim) -> dict:
    """Serialize a claim for the API (Spec 02 claim payload)."""
    return {
        "id": claim.pk,
        "seller_code": claim.seller.seller_code,
        "wallet": claim.wallet.address,
        "wallet_id": claim.wallet_id,
        "reward": claim.reward_id,
        "amount": str(claim.amount),
        "amount_smallest_unit": claim.amount_smallest_unit,
        "token_symbol": claim.token_symbol,
        "chain_id": claim.chain_id,
        "status": claim.status,
        "transaction_hash": claim.transaction_hash,
        "failure_reason": claim.failure_reason,
        "expired_at": claim.expired_at.isoformat() if claim.expired_at else None,
        "created_at": claim.created_at.isoformat(),
        "submitted_at": claim.submitted_at.isoformat() if claim.submitted_at else None,
        "confirmed_at": claim.confirmed_at.isoformat() if claim.confirmed_at else None,
    }


def submit_claim(claim, transaction_hash: str = "", *, actor=None) -> Claim:
    """Record the transaction hash the wallet broadcast (CREATED -> SUBMITTED).

    Idempotent: re-submitting the same hash returns the claim unchanged; a
    different hash for an already-submitted claim is rejected (the on-chain
    nonce makes the first transaction the only valid one).
    """
    transaction_hash = (transaction_hash or "").strip()
    with transaction.atomic():
        locked = Claim.objects.select_for_update().get(pk=claim.pk)
        if locked.status in (ClaimStatus.SUBMITTED, ClaimStatus.PENDING, ClaimStatus.CONFIRMED):
            if transaction_hash and locked.transaction_hash not in ("", transaction_hash):
                raise RewardEngineError("This claim was already submitted with another transaction.")
            return locked  # idempotent
        if locked.status not in (ClaimStatus.CREATED, ClaimStatus.SIGNING):
            raise RewardEngineError(f"Cannot submit claim in state {locked.status}.")

        locked.status = ClaimStatus.SUBMITTED
        fields = ["status"]
        if transaction_hash:
            locked.transaction_hash = transaction_hash
            fields.append("transaction_hash")
        locked.submitted_at = timezone.now()
        fields.append("submitted_at")
        locked.save(update_fields=fields)
        AuditLog.objects.create(
            actor=actor,
            action="CLAIM_SUBMITTED",
            object_type="Claim",
            object_id=str(locked.pk),
            metadata={
                "amount": str(locked.amount),
                "token": locked.token_symbol,
                "transaction_hash": transaction_hash,
            },
        )
    return locked


def mark_claim_failed(claim, reason, *, actor=None) -> Claim:
    """Mark a claim FAILED (e.g. tx reverted / out of gas)."""
    with transaction.atomic():
        locked = Claim.objects.select_for_update().get(pk=claim.pk)
        if locked.status == ClaimStatus.FAILED:
            return locked
        locked.status = ClaimStatus.FAILED
        locked.failure_reason = reason[:255]
        locked.save(update_fields=["status", "failure_reason"])
        AuditLog.objects.create(
            actor=actor,
            action="CLAIM_FAILED",
            object_type="Claim",
            object_id=str(locked.pk),
            metadata={"reason": reason},
        )
    return locked


def mark_claim_expired(claim, *, actor=None) -> Claim:
    """Expire a claim past its deadline and restore the reward to AVAILABLE.

    The on-chain authorization is non-replayable via its nonce, so a fresh
    claim (new nonce) is safe to create afterwards.
    """
    with transaction.atomic():
        locked = Claim.objects.select_for_update().get(pk=claim.pk)
        if locked.status == ClaimStatus.EXPIRED:
            return locked
        if locked.status == ClaimStatus.CONFIRMED:
            raise RewardEngineError("Cannot expire a confirmed claim.")

        locked.status = ClaimStatus.EXPIRED
        locked.save(update_fields=["status"])

        if locked.reward:
            reward = Reward.objects.select_for_update().get(pk=locked.reward.pk)
            if reward.status not in (RewardStatus.CLAIMED, RewardStatus.REVERSED):
                reward.status = RewardStatus.AVAILABLE
                reward.save(update_fields=["status"])
            locked.reward = reward

        AuditLog.objects.create(
            actor=actor,
            action="CLAIM_EXPIRED",
            object_type="Claim",
            object_id=str(locked.pk),
            metadata={"amount": str(locked.amount), "token": locked.token_symbol},
        )
    return locked


def mark_claim_confirmed(claim, transaction_hash, *, actor=None) -> Claim:
    """Mark a claim CONFIRMED after the on-chain listener sees the event."""
    with transaction.atomic():
        locked = Claim.objects.select_for_update().get(pk=claim.pk)
        locked.status = ClaimStatus.CONFIRMED
        locked.transaction_hash = transaction_hash
        locked.confirmed_at = timezone.now()
        locked.save(update_fields=["status", "transaction_hash", "confirmed_at"])

        # The reward lifecycle: CLAIMED.
        if locked.reward and locked.reward.status != RewardStatus.CLAIMED:
            reward = Reward.objects.select_for_update().get(pk=locked.reward.pk)
            reward.status = RewardStatus.CLAIMED
            reward.save(update_fields=["status"])
            locked.reward = reward

        from apps.blockchain.ledger import record  # noqa: PLC0415 - lazy: avoids an import cycle
        from apps.blockchain.models import LedgerAction  # noqa: PLC0415 - lazy import

        record(
            LedgerAction.CLAIM_CONFIRMED,
            seller=locked.seller,
            reward=locked.reward,
            claim=locked,
            wallet=locked.wallet,
            token_symbol=locked.token_symbol,
            amount=locked.amount,
            amount_smallest_unit=locked.amount_smallest_unit,
            transaction_hash=transaction_hash,
        )
        AuditLog.objects.create(
            actor=actor,
            action="CLAIM_CONFIRMED",
            object_type="Claim",
            object_id=str(locked.pk),
            metadata={"transaction_hash": transaction_hash},
        )
    return locked
