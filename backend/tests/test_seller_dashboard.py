"""The seller dashboard summary (Spec 01).

`GET /me/dashboard/` is the call the onboarding page makes the instant a wallet
connects. It had no coverage at all, so a Decimal/Integer mix inside its Coalesce
aggregates answered 500 in the browser while the suite stayed green.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.rewards.models import Reward, RewardStatus

from .helpers import make_campaign, make_user, make_verified_post

User = get_user_model()


class SellerDashboardTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user, self.profile = make_user()
        self.client.force_authenticate(self.user)

    def _reward(self, campaign, amount, status):
        return Reward.objects.create(
            seller=self.profile,
            campaign=campaign,
            amount=Decimal(amount),
            gross_amount=Decimal(amount),
            token_symbol="TST",
            chain_id=46630,
            status=status,
        )

    def test_empty_dashboard_serialises_decimal_zeroes(self):
        # The regression: `Coalesce(Sum("amount"), 0)` mixed a Decimal with an
        # integer literal and raised FieldError, so a seller with no rewards got a
        # 500 instead of a zeroed summary.
        resp = self.client.get("/api/v1/me/dashboard/")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(resp.data["total_earnings"]), Decimal("0"))
        self.assertEqual(Decimal(resp.data["available_to_claim"]), Decimal("0"))
        self.assertEqual(resp.data["pending_rewards"], 0)
        self.assertEqual(resp.data["posts_tracked"], 0)
        self.assertEqual(resp.data["verified_posts"], 0)
        self.assertEqual(resp.data["total_engagement"], 0)

    def test_only_available_rewards_are_claimable(self):
        campaign = make_campaign()
        self._reward(campaign, "3.5", RewardStatus.AVAILABLE)
        self._reward(campaign, "1.25", RewardStatus.PENDING)

        resp = self.client.get("/api/v1/me/dashboard/")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(resp.data["total_earnings"]), Decimal("4.75"))
        self.assertEqual(Decimal(resp.data["available_to_claim"]), Decimal("3.5"))
        self.assertEqual(resp.data["pending_rewards"], 1)

    def test_sums_fractional_decimal_amounts(self):
        # Values kept exact in binary on purpose: the test database is SQLite,
        # which stores DecimalField as a float, so an 18-decimal-place sum would
        # be a test of the engine rather than of this aggregate.
        campaign = make_campaign()
        self._reward(campaign, "0.5", RewardStatus.AVAILABLE)
        self._reward(campaign, "0.25", RewardStatus.AVAILABLE)

        resp = self.client.get("/api/v1/me/dashboard/")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(resp.data["total_earnings"]), Decimal("0.75"))
        self.assertEqual(Decimal(resp.data["available_to_claim"]), Decimal("0.75"))

    def test_post_counts_and_engagement(self):
        campaign = make_campaign()
        post = make_verified_post(self.profile, campaign, external_id="1")
        post.total_engagement = 7
        post.save(update_fields=["total_engagement"])
        make_verified_post(self.profile, campaign, external_id="2")

        resp = self.client.get("/api/v1/me/dashboard/")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["posts_tracked"], 2)
        self.assertEqual(resp.data["verified_posts"], 2)
        self.assertEqual(resp.data["total_engagement"], 7)

    def test_requires_authentication(self):
        resp = APIClient().get("/api/v1/me/dashboard/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_a_user_without_a_seller_profile_is_a_404(self):
        user = User.objects.create_user(
            username="noseller", email="noseller@example.com", password="Testpass123!"
        )
        client = APIClient()
        client.force_authenticate(user)

        resp = client.get("/api/v1/me/dashboard/")

        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
