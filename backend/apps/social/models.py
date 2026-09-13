"""X integration models (Specs 02 & 03).

OAuth credentials are stored encrypted at rest; raw tokens are never logged.
"""
from django.db import models
from django.utils import timezone

from apps.sellers.models import SellerProfile


class XAccount(models.Model):
    """A seller's linked X (Twitter) account."""

    seller = models.ForeignKey(SellerProfile, on_delete=models.CASCADE, related_name="x_accounts")
    provider_user_id = models.CharField(max_length=64, db_index=True, unique=True)
    username = models.CharField(max_length=64)
    display_name = models.CharField(max_length=128, blank=True)
    avatar_url = models.URLField(blank=True)
    # Encrypted access/refresh credential references (encrypted at rest).
    encrypted_credentials = models.BinaryField(blank=True, editable=False)
    credentials_iv = models.BinaryField(blank=True, editable=False)
    token_expiry = models.DateTimeField(null=True, blank=True)
    scopes = models.JSONField(default=list, blank=True)
    connected_at = models.DateTimeField(default=timezone.now)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, default="CONNECTED")

    class Meta:
        ordering = ["-connected_at"]

    def __str__(self):
        return f"@{self.username} ({self.provider_user_id})"


class PostVerificationStatus(models.TextChoices):
    DISCOVERED = "DISCOVERED", "Discovered"
    BASIC_VALIDATION = "BASIC_VALIDATION", "Basic validation"
    CAMPAIGN_MATCH = "CAMPAIGN_MATCH", "Campaign match"
    DUPLICATE_CHECK = "DUPLICATE_CHECK", "Duplicate check"
    METRICS_PENDING = "METRICS_PENDING", "Metrics pending"
    VERIFIED = "VERIFIED", "Verified"
    REWARD_CALCULATED = "REWARD_CALCULATED", "Reward calculated"
    APPROVED = "APPROVED", "Approved"
    # Failure states
    NOT_ELIGIBLE = "NOT_ELIGIBLE", "Not eligible"
    DUPLICATE = "DUPLICATE", "Duplicate"
    OUTSIDE_CAMPAIGN_WINDOW = "OUTSIDE_CAMPAIGN_WINDOW", "Outside campaign window"
    REQUIREMENT_MISSING = "REQUIREMENT_MISSING", "Requirement missing"
    ACCOUNT_NOT_CONNECTED = "ACCOUNT_NOT_CONNECTED", "Account not connected"
    PROVIDER_ERROR = "PROVIDER_ERROR", "Provider error"
    SUSPICIOUS_ACTIVITY = "SUSPICIOUS_ACTIVITY", "Suspicious activity"


class SocialPost(models.Model):
    """A discovered qualifying post (Spec 02 & 03)."""

    x_account = models.ForeignKey(
        XAccount, on_delete=models.PROTECT, related_name="posts", null=True, blank=True
    )
    external_post_id = models.CharField(max_length=64, db_index=True, unique=True)
    seller = models.ForeignKey(SellerProfile, on_delete=models.PROTECT, related_name="posts")
    campaign = models.ForeignKey(
        "campaigns.Campaign", on_delete=models.PROTECT, related_name="posts", null=True, blank=True
    )
    post_url = models.URLField()
    text_snapshot = models.TextField(blank=True)
    published_at = models.DateTimeField()
    discovered_at = models.DateTimeField(default=timezone.now)
    verification_status = models.CharField(
        max_length=32,
        choices=PostVerificationStatus.choices,
        default=PostVerificationStatus.DISCOVERED,
        db_index=True,
    )
    rejection_reason = models.CharField(max_length=255, blank=True)
    last_metrics_sync = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Denormalized current metrics for display.
    impressions = models.BigIntegerField(default=0)
    likes = models.BigIntegerField(default=0)
    reposts = models.BigIntegerField(default=0)
    replies = models.BigIntegerField(default=0)
    quotes = models.BigIntegerField(default=0)
    bookmarks = models.BigIntegerField(default=0)
    total_engagement = models.BigIntegerField(default=0)

    class Meta:
        ordering = ["-published_at"]

    def __str__(self):
        return f"Post {self.external_post_id} ({self.verification_status})"

    def set_verification(self, status, reason=""):
        self.verification_status = status
        self.rejection_reason = reason
        self.save(update_fields=["verification_status", "rejection_reason", "updated_at"])


class PostMetricSnapshot(models.Model):
    """An immutable snapshot of a post's metrics at a point in time (Spec 03).

    Snapshots preserve history for reproducible rewards:
      10:00 = 1,000 likes
      12:00 = 1,400 likes
    """

    post = models.ForeignKey(SocialPost, on_delete=models.CASCADE, related_name="metric_snapshots")
    collected_at = models.DateTimeField(default=timezone.now)
    impressions = models.BigIntegerField(default=0)
    likes = models.BigIntegerField(default=0)
    reposts = models.BigIntegerField(default=0)
    replies = models.BigIntegerField(default=0)
    quotes = models.BigIntegerField(default=0)
    bookmarks = models.BigIntegerField(default=0)
    raw_provider_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["collected_at"]
        unique_together = ("post", "collected_at")

    def __str__(self):
        return f"Snapshot {self.collected_at.isoformat()} post={self.post_id}"