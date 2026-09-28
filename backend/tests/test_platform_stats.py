"""Platform statistics endpoint tests.

The landing page renders these figures, so they must reflect the database
exactly. An empty database must return zeros — never a placeholder — and the
paid total must only count rewards that were actually claimed.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.campaigns.models import CampaignStatus
from apps.campaigns.stats import platform_stats
from apps.rewards.models import Reward, RewardStatus
from apps.sellers.models import SellerProfile
from apps.social.models import PostVerificationStatus, SocialPost

from .helpers import make_campaign, make_user

STATS_URL = "/api/v1/campaigns/stats/"

# Post counts used in the verification-rate test: 2 verified of 3 tracked.
POSTS_TOTAL = 3
POSTS_VERIFIED = 2
CLAIMED_AMOUNT = Decimal("100")
OUTSTANDING_AMOUNT = Decimal("250")


class PlatformStatsEmptyTests(TestCase):
    """An empty database must yield zeros, not invented numbers."""

    def test_endpoint_returns_zeros_on_empty_database(self):
        resp = APIClient().get(STATS_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data
        self.assertEqual(data["rewards_paid_total"], "0")
        self.assertEqual(data["rewards_outstanding_total"], "0")
        self.assertEqual(data["claims_completed"], 0)
        self.assertEqual(data["active_sellers"], 0)
        self.assertEqual(data["campaigns_live"], 0)
        self.assertEqual(data["posts_tracked"], 0)
        self.assertIsNone(data["verification_rate"])

    def test_endpoint_is_public(self):
        # No credentials: the landing page fetches this before anyone signs in.
        self.assertEqual(APIClient().get(STATS_URL).status_code, status.HTTP_200_OK)

    def test_url_name_resolves(self):
        self.assertEqual(reverse("campaigns:platform-stats"), STATS_URL)


class PlatformStatsAggregationTests(TestCase):
    def test_paid_total_counts_only_claimed_rewards(self):
        _, profile = make_user()
        claimed = make_campaign(slug="claimed-campaign")
        pending = make_campaign(slug="pending-campaign")

        Reward.objects.create(
            seller=profile, campaign=claimed, amount=CLAIMED_AMOUNT,
            gross_amount=CLAIMED_AMOUNT, token_symbol="RWD", chain_id=46630,
            status=RewardStatus.CLAIMED,
        )
        Reward.objects.create(
            seller=profile, campaign=pending, amount=OUTSTANDING_AMOUNT,
            gross_amount=OUTSTANDING_AMOUNT, token_symbol="RWD", chain_id=46630,
            status=RewardStatus.AVAILABLE,
        )

        stats = platform_stats()
        # The claimed one is paid; the available one is still owed. They must
        # not be merged into a single headline number.
        self.assertEqual(stats["rewards_paid_total"], "100")
        self.assertEqual(stats["rewards_outstanding_total"], "250")
        self.assertEqual(stats["claims_completed"], 1)

    def test_sellers_and_campaigns_counted_by_status(self):
        make_user()
        make_campaign(slug="live-campaign")
        make_campaign(slug="draft-campaign", status=CampaignStatus.DRAFT)

        stats = platform_stats()
        self.assertEqual(stats["active_sellers"], 1)
        self.assertEqual(stats["campaigns_live"], 1)  # only the ACTIVE one
        self.assertEqual(stats["campaigns_total"], 2)

    def test_verification_rate_is_a_ratio_not_a_percentage(self):
        _, profile = make_user()
        campaign = make_campaign()
        for i in range(POSTS_TOTAL):
            SocialPost.objects.create(
                seller=profile,
                campaign=campaign,
                external_post_id=f"1000{i}",
                post_url=f"https://x.com/seller/status/{1000 + i}",
                published_at=timezone.now(),
                verification_status=(
                    PostVerificationStatus.VERIFIED
                    if i < POSTS_VERIFIED
                    else PostVerificationStatus.DISCOVERED
                ),
            )

        stats = platform_stats()
        self.assertEqual(stats["posts_tracked"], POSTS_TOTAL)
        self.assertEqual(stats["posts_verified"], POSTS_VERIFIED)
        # A 0-1 ratio, not 66.67 — the frontend multiplies by 100.
        self.assertEqual(stats["verification_rate"], 0.6667)

    def test_inactive_sellers_excluded(self):
        user, profile = make_user()
        profile.status = SellerProfile.Status.SUSPENDED
        profile.save()
        self.assertEqual(platform_stats()["active_sellers"], 0)

    def test_does_not_leak_seller_or_campaign_detail(self):
        make_user()
        make_campaign()
        data = APIClient().get(STATS_URL).data
        # Aggregates only: no names, handles, slugs or wallet addresses.
        for key in data:
            self.assertIsInstance(data[key], (int, str, float, type(None)))
        serialised = str(data)
        for leaked in ("@", "0x", "username", "slug"):
            self.assertNotIn(leaked, serialised)
