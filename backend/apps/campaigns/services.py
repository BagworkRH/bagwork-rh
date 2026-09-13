"""Campaign business logic (eligibility rules, joining)."""
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.rewards.exceptions import RewardEngineError
from apps.sellers.models import SellerProfile

from .models import CampaignParticipation, CampaignStatus


def join_campaign(seller, campaign, *, actor=None) -> CampaignParticipation:
    """Validate eligibility and join a campaign (Spec 03).

    Ineligible sellers are rejected with a clear reason. Raises
    RewardEngineError with a user-safe message.
    """
    if seller.status != SellerProfile.Status.ACTIVE:
        raise RewardEngineError("Your seller account is not active.")

    if campaign.status != CampaignStatus.ACTIVE:
        raise RewardEngineError("This campaign is not currently accepting participants.")

    now = timezone.now()
    if now < campaign.start_at:
        raise RewardEngineError(f"This campaign starts on {campaign.start_at.isoformat()}.")
    if now > campaign.end_at:
        raise RewardEngineError("This campaign has ended.")

    req = campaign.requirements_json or {}
    if req.get("minimum_followers"):
        score = seller.reputation_score
        min_followers = int(req.get("minimum_followers"))
        if score < min_followers:
            raise RewardEngineError(
                f"This campaign requires a reputation score of at least {min_followers}."
            )

    participation, created = CampaignParticipation.objects.get_or_create(
        seller=seller, campaign=campaign
    )
    if not created:
        if participation.status == "ACTIVE":
            # Idempotent re-join.
            return participation
        participation.status = "ACTIVE"
        participation.save(update_fields=["status"])

    AuditLog.objects.create(
        actor=actor,
        action="CAMPAIGN_JOINED",
        object_type="Campaign",
        object_id=str(campaign.pk),
        metadata={"seller_code": seller.seller_code, "campaign": campaign.slug},
    )
    return participation