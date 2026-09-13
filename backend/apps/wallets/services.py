"""Wallet connection and ownership verification (Spec 04).

Ownership of a wallet is proven by a signature over a server-issued nonce,
never by the address alone.
"""
import secrets
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.rewards.exceptions import RewardEngineError
from apps.rewards.models import Reward, RewardStatus

from .models import Claim, ClaimStatus, Wallet

# Message sellers are asked to sign. The address and nonce make signature
# replies non-replayable and bound to a specific wallet.
NONCE_MESSAGE_TEMPLATE = (
    "CryptoSocialRewards: verify wallet ownership.\n"
    "Wallet: {address}\nChain: {chain_id}\nNonce: {nonce}"
)


def _normalize_address(address: str) -> str:
    return address.strip().lower()


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


def verify_wallet_signature(wallet, address, chain_id, signature, *, actor=None) -> Wallet:
    """Verify the signature produced by the wallet over the nonce message.

    Uses dedicated signature recovery: only an address whose private key
    signed the nonce message can prove ownership.
    """
    from eth_account import Account  # noqa: PLC0415  (heavy dep, imported only when used)

    address = _normalize_address(address)
    if _normalize_address(wallet.address) != address:
        raise RewardEngineError("Signature wallet address does not match.")

    # This must match what the frontend signed.
    message = NONCE_MESSAGE_TEMPLATE.format(
        address=wallet.address, chain_id=chain_id, nonce=wallet.nonce
    )
    signed_message = Account.recover_message(
        Account._encode_defunct(text=message), signature=signature
    )
    recovered = _normalize_address(signed_message)
    if recovered != _normalize_address(wallet.address):
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
    """
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

        token_decimals = 18
        amount_smallest = int(reward_locked.amount * (Decimal(10) ** token_decimals))
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
            expired_at=timezone.now() + timezone.timedelta(hours=24),
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

        AuditLog.objects.create(
            actor=actor,
            action="CLAIM_CONFIRMED",
            object_type="Claim",
            object_id=str(locked.pk),
            metadata={"transaction_hash": transaction_hash},
        )
    return locked
