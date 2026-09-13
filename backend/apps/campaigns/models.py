"""Campaign and participation models (Spec 02)."""
from django.db import models
from django.utils import timezone

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