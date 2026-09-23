"""Blockchain domain models (Spec 04).

- TokenConfig: allowlist of reward tokens per chain.
- PlatformControl: runtime emergency controls (claiming pause).
- LedgerEntry: append-only internal accounting ledger. The blockchain balance is
  NOT the same as this ledger — reconciliation compares both (Spec 04).
"""
from django.db import models
from django.utils import timezone

from apps.sellers.models import SellerProfile
from apps.wallets.models import Claim, Wallet


class TokenConfig(models.Model):
    """A reward token allowed on the platform (validate against allowlist)."""

    symbol = models.CharField(max_length=16, unique=True)
    chain_id = models.PositiveIntegerField(db_index=True)
    address = models.CharField(max_length=42, unique=True)
    decimals = models.PositiveSmallIntegerField(default=18)
    minimum_claim = models.DecimalField(max_digits=40, decimal_places=18, default=0)
    maximum_claim = models.DecimalField(max_digits=40, decimal_places=18, default=0)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["symbol"]

    def __str__(self):
        return f"{self.symbol} (chain {self.chain_id})"


class PlatformControl(models.Model):
    """Runtime emergency controls (Spec 04: pause claiming, disable tokens)."""

    key = models.CharField(max_length=64, unique=True, default="claiming")
    claiming_paused = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"claiming_paused={self.claiming_paused}"


class LedgerAction(models.TextChoices):
    REWARD_EARNED = "REWARD_EARNED", "Reward earned"
    REWARD_APPROVED = "REWARD_APPROVED", "Reward approved"
    CLAIM_CREATED = "CLAIM_CREATED", "Claim created"
    CLAIM_CONFIRMED = "CLAIM_CONFIRMED", "Claim confirmed on-chain"
    CLAIM_FAILED = "CLAIM_FAILED", "Claim failed"
    RECONCILIATION = "RECONCILIATION", "Reconciliation note"


class LedgerEntry(models.Model):
    """Append-only internal accounting entry (Spec 04)."""

    action = models.CharField(max_length=24, choices=LedgerAction.choices, db_index=True)
    seller = models.ForeignKey(
        SellerProfile, on_delete=models.PROTECT, related_name="ledger_entries", null=True, blank=True
    )
    reward = models.ForeignKey(
        "rewards.Reward", on_delete=models.PROTECT, related_name="ledger_entries",
        null=True, blank=True,
    )
    claim = models.ForeignKey(
        Claim, on_delete=models.PROTECT, related_name="ledger_entries", null=True, blank=True
    )
    wallet = models.ForeignKey(
        Wallet, on_delete=models.PROTECT, related_name="ledger_entries", null=True, blank=True
    )
    token_symbol = models.CharField(max_length=16, blank=True)
    amount = models.DecimalField(max_digits=40, decimal_places=18, default=0)
    amount_smallest_unit = models.BigIntegerField(default=0)
    transaction_hash = models.CharField(max_length=66, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} {self.amount} {self.token_symbol}"