"""Seller account administration (Spec 05 Phase 7 admin).

Seller status changes are sensitive actions: they always go through this module
so they are audited, and they never silently touch historical financial data.
"""
from django.db import transaction

from apps.audit.models import AuditLog
from apps.rewards.exceptions import RewardEngineError

from .models import SellerProfile

# Reputation score bounds (Spec 02): 0-100, used for campaign eligibility.
REPUTATION_MIN = 0
REPUTATION_MAX = 100


def set_seller_status(seller, new_status, reason="", *, actor=None) -> SellerProfile:
    """Activate, suspend, or re-pend a seller profile.

    Suspension blocks new campaign joins (see `apps.campaigns.services`) and
    claiming (`apps.wallets.services.create_claim`); existing rewards and claims
    are never deleted or rewritten.
    """
    if new_status not in SellerProfile.Status.values:
        raise RewardEngineError(
            "status must be one of: " + ", ".join(SellerProfile.Status.values) + "."
        )

    with transaction.atomic():
        locked = SellerProfile.objects.select_for_update().get(pk=seller.pk)
        previous = locked.status
        locked.status = new_status
        locked.save(update_fields=["status", "updated_at"])

    AuditLog.objects.create(
        actor=actor,
        action="SELLER_STATUS_CHANGED",
        object_type="SellerProfile",
        object_id=str(locked.pk),
        metadata={
            "seller_code": locked.seller_code,
            "from": previous,
            "to": new_status,
            "reason": reason,
        },
    )
    return locked


def set_reputation(seller, score, reason="", *, actor=None) -> SellerProfile:
    """Adjust a seller's reputation score (0-100) with an audit trail."""
    try:
        value = int(score)
    except (TypeError, ValueError) as exc:
        raise RewardEngineError("reputation score must be an integer 0-100.") from exc
    if not REPUTATION_MIN <= value <= REPUTATION_MAX:
        raise RewardEngineError("reputation score must be between 0 and 100.")

    with transaction.atomic():
        locked = SellerProfile.objects.select_for_update().get(pk=seller.pk)
        previous = locked.reputation_score
        locked.reputation_score = value
        locked.save(update_fields=["reputation_score", "updated_at"])

    AuditLog.objects.create(
        actor=actor,
        action="SELLER_REPUTATION_CHANGED",
        object_type="SellerProfile",
        object_id=str(locked.pk),
        metadata={
            "seller_code": locked.seller_code,
            "from": previous,
            "to": value,
            "reason": reason,
        },
    )
    return locked