"""Campaign and participation models (Spec 02)."""
from datetime import timezone as dt_timezone

from django.db import models
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.sellers.models import SellerProfile


class CampaignStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    ACTIVE = "ACTIVE", "Active"
    PAUSED = "PAUSED", "Paused"
    ENDED = "ENDED", "Ended"
    CANCELLED = "CANCELLED", "Cancelled"


class RewardModel(models.TextChoices):
    FIXED = "FIXED", "Fixed per post"
    IMPRESSION_BASED = "IMPRESSION_BASED", "Per 1k impressions"
    ENGAGEMENT_BASED = "ENGAGEMENT_BASED", "Per 100 engagements"
    HYBRID = "HYBRID", "Fixed + engagement"


class Campaign(models.Model):
    """A reward campaign that sellers join and earn against (Spec 02)."""

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    project_name = models.CharField(max_length=255)
    token_symbol = models.CharField(max_length=16)
    chain_id = models.PositiveIntegerField()
    budget = models.DecimalField(max_digits=40, decimal_places=18)
    # Remaining budget is deducted transactionally when rewards are approved.
    remaining_budget = models.DecimalField(max_digits=40, decimal_places=18)
    reward_model = models.CharField(max_length=32, choices=RewardModel.choices)
    reward_rate = models.DecimalField(max_digits=40, decimal_places=18, default=0)
    maximum_reward_per_seller = models.DecimalField(
        max_digits=40, decimal_places=18, default=0
    )
    maximum_rewards_per_seller = models.PositiveIntegerField(default=0)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    status = models.CharField(
        max_length=16, choices=CampaignStatus.choices, default=CampaignStatus.DRAFT
    )
    # JSON requirements such as required hashtags, mentions, minimum followers.
    requirements_json = models.JSONField(default=dict, blank=True)
    # High-water mark for discovery polling, per platform. Stored here rather
    # than globally so a new campaign re-reads its whole window while an
    # in-flight one only reads what is new. Polling with no watermark would
    # re-scan history every tick and burn credits for nothing.
    discovery_watermarks = models.JSONField(default=dict, blank=True)
    # Which brand funds this campaign. Null means staff-funded (platform-funded
    # campaigns during development), which skips the funding check at launch.
    # Set on creation from the brand's own account so a campaign cannot be
    # attributed to another brand's money.
    funding_brand = models.ForeignKey(
        "campaigns.BrandProfile",
        on_delete=models.PROTECT,
        related_name="campaigns",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="campaigns"
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def is_active_for_joining(self, at=None):
        at = at or timezone.now()
        return self.status == CampaignStatus.ACTIVE and self.start_at <= at <= self.end_at

    def discovery_watermark(self, platform: str):
        """When this campaign last polled `platform`; None on a first run."""
        raw = (self.discovery_watermarks or {}).get(platform)
        if not raw:
            return None
        parsed = parse_datetime(raw)
        return parsed if parsed and timezone.is_aware(parsed) else None

    def set_discovery_watermark(self, platform: str, when) -> None:
        """Record the high-water mark after a successful poll."""
        if when is None:
            when = timezone.now()
        marks = dict(self.discovery_watermarks or {})
        marks[platform] = when.astimezone(dt_timezone.utc).isoformat()
        self.discovery_watermarks = marks
        self.save(update_fields=["discovery_watermarks", "updated_at"])


class BrandStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    ACTIVE = "ACTIVE", "Active"
    SUSPENDED = "SUSPENDED", "Suspended"


class BrandProfile(models.Model):
    """A brand is the paying customer: the company that funds a campaign.

    Separate from SellerProfile because a brand has the opposite interest.
    A seller wants to be paid; a brand wants verifiable work for the least
    money and can end a campaign. A user may hold one of each, and holding
    both is legitimate (a company running its own creator campaign), so
    neither is derived from the other.
    """

    user = models.OneToOneField(
        "accounts.User", on_delete=models.CASCADE, related_name="brand_profile"
    )
    company_name = models.CharField(max_length=255)
    # Human-facing contact. Not an authentication factor; auth stays on User.
    contact_email = models.EmailField(blank=True)
    # This brand's on-chain address, used to attribute incoming stablecoin.
    funding_wallet = models.CharField(max_length=42, blank=True)
    status = models.CharField(
        max_length=16, choices=BrandStatus.choices, default=BrandStatus.PENDING
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.company_name} ({self.user.email})"

    @property
    def is_active(self) -> bool:
        return self.status == BrandStatus.ACTIVE


class FundingStatus(models.TextChoices):
    PENDING = "PENDING", "Awaiting confirmation"
    CONFIRMED = "CONFIRMED", "Confirmed"
    REJECTED = "REJECTED", "Rejected"


class BrandFunding(models.Model):
    """A brand funding deposit, in the platform stablecoin (USDG by default).

    Brands pay in stablecoin and creators are paid in the same stablecoin, so the
    platform never converts to fiat and never becomes an exchanger.

    The stablecoin is dollar-denominated precisely so a creator payout holds its
    value. Paying creators in the platform token instead would expose the people
    doing the work to its price, which is the failure mode the payout design
    exists to avoid.

    Replay protection is the load-bearing concern: a deposit is credited from
    an on-chain transfer, and the same transfer must never fund two campaigns
    or be re-submitted to inflate a balance. `tx_hash` is therefore unique per
    chain, which makes double-crediting impossible at the database level
    rather than relying on application logic staying correct.
    """

    brand = models.ForeignKey(BrandProfile, on_delete=models.PROTECT, related_name="fundings")
    # 18 decimal places, wider than any allowlisted token needs (USDG, the
    # funding token, is 6 on both Robinhood Chain networks — read from the
    # chain, not assumed). A column sized to the narrowest token would have to
    # be widened later, and widening it rounds existing deposits off-cent, so
    # they stop matching the payouts they were sent to fund.
    amount = models.DecimalField(max_digits=40, decimal_places=18)
    chain_id = models.PositiveIntegerField()
    token_symbol = models.CharField(
        max_length=16,
        # Default is applied in the service from settings.FUNDING_TOKEN_SYMBOL
        # rather than hardcoded, so the funding token has a single definition.
        # Kept in sync by `record_funding`.
        default="USDG",
    )
    tx_hash = models.CharField(max_length=66)
    status = models.CharField(
        max_length=16, choices=FundingStatus.choices, default=FundingStatus.PENDING
    )
    # Optional allocation to one campaign. Null = unallocated brand balance,
    # available to the brand's next campaign.
    campaign = models.ForeignKey(
        "campaigns.Campaign", on_delete=models.PROTECT, related_name="fundings", null=True, blank=True
    )
    funded_at = models.DateTimeField(default=timezone.now)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    # What the chain actually said at confirmation time. A funding dispute is
    # settled by pointing at a block and a sender address, so the evidence is
    # stored rather than discarded once the check has passed. Null until a
    # confirmation has verified it: a non-null row with no evidence here would
    # mean a confirmation happened without a receipt, which is the bug these
    # fields were added to make impossible to hide.
    verified_block = models.BigIntegerField(null=True, blank=True)
    verified_confirmations = models.PositiveIntegerField(null=True, blank=True)
    verified_sender = models.CharField(max_length=42, null=True, blank=True)
    verified_amount = models.DecimalField(
        max_digits=40, decimal_places=18, null=True, blank=True
    )

    class Meta:
        ordering = ["-funded_at"]
        constraints = [
            # A given on-chain transfer can be recorded once, ever. The
            # application-level check is only a fast path for a friendlier
            # error message; this constraint is what actually prevents it.
            models.UniqueConstraint(
                fields=["chain_id", "tx_hash"], name="unique_funding_per_chain_tx"
            )
        ]

    def __str__(self):
        return f"{self.amount} {self.token_symbol} for {self.brand.company_name} ({self.status})"

    @property
    def is_confirmed(self) -> bool:
        return self.status == FundingStatus.CONFIRMED


class ParticipationStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    LEFT = "LEFT", "Left"
    EXCLUDED = "EXCLUDED", "Excluded"


class CampaignParticipation(models.Model):
    """A seller who joined a campaign (Spec 02)."""

    seller = models.ForeignKey(SellerProfile, on_delete=models.PROTECT, related_name="participations")
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="participations")
    status = models.CharField(
        max_length=16, choices=ParticipationStatus.choices, default=ParticipationStatus.ACTIVE
    )
    joined_at = models.DateTimeField(default=timezone.now)
    cumulative_reward = models.DecimalField(max_digits=40, decimal_places=18, default=0)

    class Meta:
        ordering = ["-joined_at"]
        unique_together = ("seller", "campaign")

    def __str__(self):
        return f"{self.seller.seller_code} in {self.campaign.name}"
