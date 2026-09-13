"""Reward model and statuses (Spec 02 & 03)."""
from django.db import models
from django.utils import timezone

from apps.sellers.models import SellerProfile


class RewardStatus(models.TextChoices):
    PENDING = "PENDING", "Pending verification"
    VERIFIED = "VERIFIED", "Verified"
    APPROVED = "APPROVED", "Approved"
    AVAILABLE = "AVAILABLE", "Available to claim"
    CLAIMED = "CLAIMED", "Claimed"
    FAILED = "FAILED", "Claim failed"
    REVERSED = "REVERSED", "Reversed"


class RewardCalculationVersion(models.TextChoices):
    V1 = "V1", "Calculation version 1"


class Reward(models.Model):
    """An earned reward for a verified post (Spec 02 & 03).

    Financial precision: `amount` uses Decimal (off-chain accounting).
    The claim step converts to integer smallest token units on-chain.
    """

    seller = models.ForeignKey(SellerProfile, on_delete=models.PROTECT, related_name="rewards")
    campaign = models.ForeignKey("campaigns.Campaign", on_delete=models.PROTECT, related_name="rewards")
    post = models.OneToOneField(
        "social.SocialPost", on_delete=models.PROTECT, related_name="reward", null=True, blank=True
    )
    amount = models.DecimalField(max_digits=40, decimal_places=18)
    gross_amount = models.DecimalField(max_digits=40, decimal_places=18)
    deduction_amount = models.DecimalField(max_digits=40, decimal_places=18, default=0)
    currency = models.CharField(max_length=16, default="USDT")
    token_symbol = models.CharField(max_length=16)
    chain_id = models.PositiveIntegerField()
    calculation_version = models.CharField(
        max_length=8, choices=RewardCalculationVersion.choices, default=RewardCalculationVersion.V1
    )
    explanation = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=RewardStatus.choices, default=RewardStatus.PENDING)
    reversal_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        # A post can never earn more than one live reward.
        constraints = [
            models.UniqueConstraint(
                fields=["post", "status"],
                name="unique_live_reward_per_post",
                condition=models.Q(
                    status__in=[
                        RewardStatus.PENDING,
                        RewardStatus.VERIFIED,
                        RewardStatus.APPROVED,
                        RewardStatus.AVAILABLE,
                    ]
                ),
            )
        ]

    def __str__(self):
        return f"Reward {self.pk} {self.amount} {self.token_symbol} ({self.status})"