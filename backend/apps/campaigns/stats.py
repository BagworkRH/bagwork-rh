"""Public platform statistics for the landing page.

Aggregates only — no seller, campaign or post detail is exposed. The numbers
shown on the marketing site come from here so the site can never display
figures the database does not support.
"""
from decimal import Decimal

from django.db.models import Sum

from apps.campaigns.models import Campaign, CampaignStatus
from apps.rewards.models import Reward, RewardStatus
from apps.sellers.models import SellerProfile
from apps.social.models import PostVerificationStatus, SocialPost

# A reward only counts as "paid out" once it has actually been claimed.
PAID_REWARD_STATUSES = (RewardStatus.CLAIMED,)
# ...and a post only counts as verified once the pipeline says so.
VERIFIED = PostVerificationStatus.VERIFIED


def platform_stats() -> dict:
    """Return the public headline figures.

    All values are computed from live rows; an empty database yields zeros
    rather than placeholders.
    """
    rewards = Reward.objects.all()
    paid = rewards.filter(status__in=PAID_REWARD_STATUSES).aggregate(
        total=Sum("amount")
    )["total"]
    # A pending/approved reward is still owed, so surface it separately rather
    # than folding it into the paid total.
    outstanding = rewards.exclude(status__in=PAID_REWARD_STATUSES).aggregate(
        total=Sum("amount")
    )["total"]

    posts = SocialPost.objects.all()
    posts_total = posts.count()
    posts_verified = posts.filter(verification_status=VERIFIED).count()
    verification_rate = (
        round(posts_verified / posts_total, 4) if posts_total else None
    )

    return {
        "rewards_paid_total": str(paid or Decimal("0")),
        "rewards_outstanding_total": str(outstanding or Decimal("0")),
        "claims_completed": rewards.filter(status=RewardStatus.CLAIMED).count(),
        "active_sellers": SellerProfile.objects.filter(
            status=SellerProfile.Status.ACTIVE
        ).count(),
        "campaigns_live": Campaign.objects.filter(
            status=CampaignStatus.ACTIVE
        ).count(),
        "campaigns_total": Campaign.objects.count(),
        "posts_tracked": posts_total,
        "posts_verified": posts_verified,
        "verification_rate": verification_rate,
    }
