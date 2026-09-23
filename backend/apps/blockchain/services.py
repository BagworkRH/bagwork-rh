"""Blockchain service layer (Spec 04).

All chain I/O and claim signing live behind this module so the rest of the
application never depends on a raw provider/RPC. When `RPC_URL` /
`CONTRACT_ADDRESS` are unset the chain features report *disabled* rather than
raising, so the platform keeps working without a node.
"""
from datetime import timedelta

from django.conf import settings
from django.db import models as dj_models
from django.utils import timezone
from web3 import Web3

from apps.audit.models import AuditLog
from apps.wallets.models import Claim, ClaimStatus

from . import abi, signing
from .models import PlatformControl, TokenConfig


class BlockchainError(Exception):
    """User-safe blockchain domain error."""


class SigningUnavailableError(BlockchainError):
    """Raised when the claim signer key is not configured."""


def get_web3():
    """Return a connected Web3 instance or None when RPC is not configured."""
    if not settings.RPC_URL:
        return None
    try:  # pragma: no cover - depends on live RPC
        w3 = Web3(Web3.HTTPProvider(settings.RPC_URL))
        return w3 if w3.is_connected() else None
    except Exception:
        return None


def chain_enabled() -> bool:
    return bool(settings.RPC_URL and settings.CONTRACT_ADDRESS)


def distributor_sign() -> bool:
    return bool(settings.CLAIM_SIGNER)


def get_token_config(chain_id, symbol) -> TokenConfig:
    """Validate a token against the allowlist (Spec 04)."""
    token = TokenConfig.objects.filter(chain_id=chain_id, symbol__iexact=symbol).first()
    if token is None:
        raise BlockchainError(f"Token {symbol} is not on the allowlist for chain {chain_id}.")
    if not token.enabled:
        raise BlockchainError(f"Token {symbol} is disabled for claiming.")
    return token


def get_token_config_or_none(chain_id, symbol):
    try:
        return get_token_config(chain_id, symbol)
    except BlockchainError:
        return None


def default_token_decimals() -> int:
    return int(getattr(settings, "DEFAULT_TOKEN_DECIMALS", 18))


def claim_signer_address() -> str:
    if settings.CLAIM_SIGNER:
        return signing.signer_address(settings.CLAIM_SIGNER)
    return settings.CLAIM_SIGNER_ADDRESS or ""


def get_claim_authorization_payload(claim) -> dict:
    """Build (and cache) the signed EIP-712 claim authorization.

    Returns everything a wallet client needs to submit the claim transaction:
    the domain-separated typed data, the platform signer's signature, and the
    fully ABI-encoded calldata for `RewardDistributor.claim(...)`.

    Requires the platform claim signer key to be configured; while issuing a
    signature the claim moves to SIGNING (a valid authorization now exists).
    """
    if not settings.CONTRACT_ADDRESS:
        raise BlockchainError("CONTRACT_ADDRESS is not configured.")

    token = get_token_config(claim.chain_id, claim.token_symbol)
    deadline = signing.claim_deadline(claim.expired_at)
    nonce_int = int(claim.nonce, 16)

    digest = signing.build_claim_digest(
        wallet=claim.wallet.address,
        reward_id=claim.reward_id or 0,
        token_address=token.address,
        amount=claim.amount_smallest_unit,
        nonce=nonce_int,
        deadline=deadline,
        chain_id=claim.chain_id,
        contract_address=settings.CONTRACT_ADDRESS,
    )

    if distributor_sign():
        signature = signing.sign_claim_digest(digest, settings.CLAIM_SIGNER)
        updates = []
        if claim.signed_authorization != signature:
            claim.signed_authorization = signature
            updates.append("signed_authorization")
        if claim.status == ClaimStatus.CREATED:
            claim.status = ClaimStatus.SIGNING
            updates.append("status")
        if updates:
            claim.save(update_fields=updates)
    elif claim.signed_authorization:
        signature = claim.signed_authorization
    else:
        raise SigningUnavailableError(
            "Claim signer is not configured; cannot authorize a claim yet."
        )

    calldata = abi.encode_claim_calldata(
        reward_id=claim.reward_id or 0,
        wallet=claim.wallet.address,
        amount=claim.amount_smallest_unit,
        nonce=nonce_int,
        deadline=deadline,
        signature=signature,
    )

    return {
        "claim_id": claim.pk,
        "status": claim.status,
        "signature": signature,
        "wallet": claim.wallet.address,
        "reward_id": claim.reward_id,
        "token": token.address,
        "token_symbol": token.symbol,
        "token_decimals": token.decimals,
        "amount_smallest_unit": claim.amount_smallest_unit,
        "amount": str(claim.amount),
        "nonce": nonce_int,
        "nonce_hex": claim.nonce,
        "deadline": deadline,
        "chain_id": claim.chain_id,
        "contract_address": settings.CONTRACT_ADDRESS,
        "signer_address": claim_signer_address(),
        "domain": {"name": "CryptoRewards", "version": "1", "chainId": claim.chain_id},
        "function": abi.CLAIM_FUNCTION_SIGNATURE,
        "transaction": {
            "to": settings.CONTRACT_ADDRESS,
            "from": claim.wallet.address,
            "value": "0x0",
            "data": calldata,
            "chain_id": claim.chain_id,
        },
    }


def verify_authorization(claim, signature: str) -> bool:
    """Verify a signature against the claim authorization (used in tests)."""
    token = get_token_config(claim.chain_id, claim.token_symbol)
    digest = signing.build_claim_digest(
        wallet=claim.wallet.address,
        reward_id=claim.reward_id or 0,
        token_address=token.address,
        amount=claim.amount_smallest_unit,
        nonce=int(claim.nonce, 16),
        deadline=signing.claim_deadline(claim.expired_at),
        chain_id=claim.chain_id,
        contract_address=settings.CONTRACT_ADDRESS,
    )
    return signing.verify_claim_signature(digest, signature, claim_signer_address())


# --------------------------------------------------------------------------- #
# Emergency controls (Spec 04)
# --------------------------------------------------------------------------- #
def is_claiming_paused() -> bool:
    control = PlatformControl.objects.filter(key="claiming").first()
    return bool(control and control.claiming_paused)


def set_claiming_paused(paused: bool, *, actor=None) -> PlatformControl:
    control, _ = PlatformControl.objects.get_or_create(key="claiming")
    control.claiming_paused = bool(paused)
    control.save(update_fields=["claiming_paused", "updated_at"])
    AuditLog.objects.create(
        actor=actor,
        action="CLAIMING_PAUSED" if paused else "CLAIMING_UNPAUSED",
        object_type="PlatformControl",
        object_id=str(control.pk),
        metadata={"paused": bool(paused)},
    )
    return control


def set_token_enabled(token: TokenConfig, enabled: bool, *, actor=None) -> TokenConfig:
    token.enabled = bool(enabled)
    token.save(update_fields=["enabled", "updated_at"])
    AuditLog.objects.create(
        actor=actor,
        action="TOKEN_DISABLED" if not enabled else "TOKEN_ENABLED",
        object_type="TokenConfig",
        object_id=str(token.pk),
        metadata={"symbol": token.symbol, "chain_id": token.chain_id},
    )
    return token


def rotate_claim_signer(new_key: str, *, actor=None):
    """Rotate the claim signer (development/runtime rotation).

    In production the signer lives in a secret manager; rotation means updating
    the secret and (on-chain) revoking the old signer address on the contract
    via `setSigner`. The audit entry records the newly active signer address —
    never the key itself.
    """
    settings.CLAIM_SIGNER = new_key
    AuditLog.objects.create(
        actor=actor,
        action="CLAIM_SIGNER_ROTATED",
        object_type="Signer",
        object_id=str(new_key or "")[:12],
        metadata={"new_signer_address": claim_signer_address()},
    )


def monitor_claim_volume(threshold_per_hour: int = 20):
    """Flag sellers with unusual claim volume (Spec 04: monitor, never accuse).

    DEVELOPMENT STUB: returns current stats; review-queue integration arrives
    with the fraud/risk queue (Phase 7).
    """
    claims = Claim.objects.filter(
        created_at__gte=timezone.now() - timedelta(hours=1)
    )
    stats = list(
        claims.values("seller__seller_code")
        .annotate(count=dj_models.Count("id"))
        .order_by("-count")
    )
    flagged = [s for s in stats if s["count"] >= threshold_per_hour]
    return {"checked": len(stats), "flagged": flagged}
