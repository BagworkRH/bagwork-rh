"""Wallet and Claim models (Specs 02 & 04).

Wallets are EVM addresses. `verified` means the seller proved ownership by
signing a server-issued nonce message (ownership is never inferred from the
address alone).
"""
from django.db import models
from django.utils import timezone

from apps.sellers.models import SellerProfile


class Wallet(models.Model):
    """A seller-owned EVM wallet address."""

    class WalletType(models.TextChoices):
        EVM = "EVM", "EVM"

    class Network(models.TextChoices):
        SEPOLIA = "sepolia", "Sepolia (testnet)"
        MAINNET = "mainnet", "Ethereum mainnet"

    seller = models.ForeignKey(SellerProfile, on_delete=models.CASCADE, related_name="wallets")
    address = models.CharField(max_length=42, db_index=True)
    chain_id = models.PositiveIntegerField()
    network = models.CharField(max_length=16, choices=Network.choices, default=Network.SEPOLIA)
    wallet_type = models.CharField(max_length=8, choices=WalletType.choices, default=WalletType.EVM)
    verified = models.BooleanField(default=False)
    nonce = models.CharField(max_length=128, blank=True)
    connected_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-connected_at"]
        unique_together = ("seller", "address", "chain_id")

    def __str__(self):
        return f"{self.address} (chain {self.chain_id})"

    def normalized_address(self):
        # EVM addresses are case-insensitive for the checksum; store lowercase.
        return self.address.lower()


class ClaimStatus(models.TextChoices):
    CREATED = "CREATED", "Created"
    SIGNING = "SIGNING", "Signing"
    SUBMITTED = "SUBMITTED", "Submitted"
    PENDING = "PENDING", "Pending"
    CONFIRMED = "CONFIRMED", "Confirmed"
    FAILED = "FAILED", "Failed"
    REPLACED = "REPLACED", "Replaced"
    EXPIRED = "EXPIRED", "Expired"


class Claim(models.Model):
    """An on-chain claim of an approved reward (Spec 04)."""

    seller = models.ForeignKey(SellerProfile, on_delete=models.PROTECT, related_name="claims")
    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name="claims")
    reward = models.OneToOneField(
        "rewards.Reward", on_delete=models.PROTECT, related_name="claim", null=True, blank=True
    )
    amount = models.DecimalField(max_digits=40, decimal_places=18)
    amount_smallest_unit = models.BigIntegerField(editable=False, null=True, blank=True)
    token_symbol = models.CharField(max_length=16)
    chain_id = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=ClaimStatus.choices, default=ClaimStatus.CREATED)
    nonce = models.CharField(max_length=128, blank=True, editable=False)
    signed_authorization = models.TextField(blank=True, editable=False)
    transaction_hash = models.CharField(max_length=66, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    submitted_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    expired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        # A seller can only have one live (un-resolved) claim per reward.
        constraints = [
            models.UniqueConstraint(
                fields=["reward", "status"],
                name="unique_open_claim_per_reward",
                condition=models.Q(
                    status__in=[
                        ClaimStatus.CREATED,
                        ClaimStatus.SIGNING,
                        ClaimStatus.SUBMITTED,
                        ClaimStatus.PENDING,
                    ]
                ),
            )
        ]

    def __str__(self):
        return f"Claim {self.pk} {self.amount} {self.token_symbol} -> {self.wallet.address}"