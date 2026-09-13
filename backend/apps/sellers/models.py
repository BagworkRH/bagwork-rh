"""Seller profile and seller-code handling.

Seller codes (Spec 03):
  - format `SELLER-XXXXXX`
  - cryptographically secure, non-sequential
  - unique, case-normalized (uppercase), difficult to guess
  - never reused after deletion; indexed in the database
"""
import secrets

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import User


class SellerProfile(models.Model):
    """A seller is a User plus a seller profile (Spec 02)."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspended"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="seller_profile")
    seller_code = models.CharField(max_length=16, unique=True, db_index=True, editable=False)
    display_name = models.CharField(max_length=150, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    reputation_score = models.PositiveIntegerField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.seller_code} ({self.user.email})"

    def save(self, *args, **kwargs):
        if not self.seller_code:
            self.seller_code = self.generate_unique_code()
        self.seller_code = self.seller_code.upper()
        super().save(*args, **kwargs)

    @staticmethod
    def generate_random_code(length=6):
        """Generate a secure, non-sequential code using `secrets`.

        Alphabet deliberately excludes visually ambiguous characters
        (0/O, 1/I/L) so codes are easy to read and type.
        """
        alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
        return "SELLER-" + "".join(secrets.choice(alphabet) for _ in range(length))

    @classmethod
    def generate_unique_code(cls):
        """Return a unique code, retrying on the vanishingly unlikely collision."""
        for _ in range(100):
            candidate = cls.generate_random_code()
            exists = cls.objects.filter(
                Q(seller_code=candidate) | Q(seller_code=candidate.upper())
            ).exists()
            if not exists:
                return candidate
        raise RuntimeError("Could not allocate a unique seller code after 100 attempts.")

    @property
    def identity(self):
        return f"@{self.user.username or self.display_name}".strip()