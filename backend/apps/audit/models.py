"""Audit log and the fraud/risk review queue (Spec 02, 03 & 05).

`AuditLog` is append-only: sensitive admin/financial actions never disappear.

`RiskFlag` implements the anti-fraud rule from Spec 03: signals produce a risk
**score** that lands in a human review queue. The platform never auto-accuses a
seller on a weak signal, and no enforcement happens without a reviewer decision.
"""
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class AuditLog(models.Model):
    """Append-only log of sensitive actions."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=64, db_index=True)
    object_type = models.CharField(max_length=64, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} {self.object_type}:{self.object_id}"


class RiskSubjectType(models.TextChoices):
    POST = "POST", "Social post"
    SELLER = "SELLER", "Seller"
    WALLET = "WALLET", "Wallet"
    CLAIM = "CLAIM", "Claim"


class RiskStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    REVIEWING = "REVIEWING", "In review"
    DISMISSED = "DISMISSED", "Dismissed"
    CONFIRMED = "CONFIRMED", "Confirmed"


class RiskSeverity(models.TextChoices):
    LOW = "LOW", "Low"
    MEDIUM = "MEDIUM", "Medium"
    HIGH = "HIGH", "High"


RISK_HIGH_SCORE = 80
RISK_MEDIUM_SCORE = 50


def severity_for_score(score: int) -> str:
    """Map a 0-100 risk score onto a review severity (Spec 03)."""
    if score >= RISK_HIGH_SCORE:
        return RiskSeverity.HIGH
    if score >= RISK_MEDIUM_SCORE:
        return RiskSeverity.MEDIUM
    return RiskSeverity.LOW


class RiskFlag(models.Model):
    """A risk signal awaiting human review (Spec 03 anti-fraud).

    A flag records *why* the platform is suspicious (`signals`) and how strong
    the combined evidence is (`score`). Reviewers dismiss or confirm it; the
    decision and note are audited (see `apps.audit.risk.resolve_flag`).
    """

    subject_type = models.CharField(max_length=16, choices=RiskSubjectType.choices)
    subject_id = models.PositiveBigIntegerField(db_index=True)
    seller = models.ForeignKey(
        "sellers.SellerProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="risk_flags",
    )
    score = models.PositiveSmallIntegerField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    severity = models.CharField(
        max_length=16, choices=RiskSeverity.choices, default=RiskSeverity.LOW
    )
    signals = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=16, choices=RiskStatus.choices, default=RiskStatus.OPEN)
    note = models.CharField(max_length=255, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_risk_flags",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "severity"])]
        # One open flag per subject: re-scoring updates the existing row instead
        # of filling the queue with duplicates.
        constraints = [
            models.UniqueConstraint(
                fields=["subject_type", "subject_id"],
                name="unique_open_risk_flag_per_subject",
                condition=models.Q(status__in=[RiskStatus.OPEN, RiskStatus.REVIEWING]),
            )
        ]

    def __str__(self):
        return f"{self.subject_type}:{self.subject_id} score={self.score} ({self.status})"