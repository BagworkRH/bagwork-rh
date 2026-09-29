"""Fixed-reward policy tests (Spec 03).

The platform pays a fixed amount per verified *original* post. These tests
pin the two things that make that promise true: reposts and quotes do not
earn, and undisclosed posts do not earn.
"""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.campaigns.models import RewardModel
from apps.campaigns.serializers import CampaignSerializer
from apps.rewards.services import compute_raw_reward
from apps.social.models import PostVerificationStatus, SocialPost
from apps.social.post_services import run_verification
from apps.social.providers.official import OfficialXProvider

from .helpers import make_campaign, make_user, make_verified_post


class OriginalityGateTests(TestCase):
    def setUp(self):
        self.user, self.profile = make_user()
        self.campaign = make_campaign()
        self.now = timezone.now()

    def _post(self, external_id, **kwargs):
        kwargs.setdefault("text_snapshot", "hello #ad")
        post = SocialPost.objects.create(
            seller=self.profile,
            campaign=self.campaign,
            external_post_id=external_id,
            post_url=f"https://x.com/i/status/{external_id}",
            published_at=self.now,
            **kwargs,
        )
        return run_verification(post)

    def test_original_disclosed_post_is_verified(self):
        post = self._post("orig-1")
        self.assertEqual(post.verification_status, PostVerificationStatus.VERIFIED)
        self.assertTrue(post.is_original)

    def test_repost_is_not_eligible(self):
        post = self._post("rep-1", is_repost=True)
        self.assertEqual(post.verification_status, PostVerificationStatus.NOT_ORIGINAL)
        self.assertIn("repost", post.rejection_reason.lower())

    def test_quote_is_not_eligible(self):
        post = self._post("quo-1", is_quote=True)
        self.assertEqual(post.verification_status, PostVerificationStatus.NOT_ORIGINAL)
        self.assertIn("quote", post.rejection_reason.lower())

    def test_undisclosed_post_is_not_eligible(self):
        campaign = make_campaign(
            slug="undisclosed-campaign",
            requirements_json={"required_disclosure": ["#ad"]},
        )
        post = SocialPost.objects.create(
            seller=self.profile,
            campaign=campaign,
            external_post_id="undisc-1",
            post_url="https://x.com/i/status/undisc-1",
            text_snapshot="no disclosure here",
            published_at=self.now,
        )
        post = run_verification(post)
        self.assertEqual(post.verification_status, PostVerificationStatus.NOT_DISCLOSED)

    def test_campaign_may_opt_into_non_original(self):
        # Kept available for research/measurement, off by default.
        campaign = make_campaign(
            slug="non-original-campaign",
            requirements_json={"allow_non_original": True},
        )
        post = SocialPost.objects.create(
            seller=self.profile,
            campaign=campaign,
            external_post_id="rep-2",
            post_url="https://x.com/i/status/rep-2",
            text_snapshot="reposted #ad",
            published_at=self.now,
            is_repost=True,
        )
        post = run_verification(post)
        self.assertEqual(post.verification_status, PostVerificationStatus.VERIFIED)


class ProviderOriginalityMappingTests(TestCase):
    """X tells us via `referenced_tweets`; if we never read it, we cannot tell."""

    def test_plain_post_maps_to_original(self):
        payload = OfficialXProvider.normalize_post(
            {"id": "1", "text": "hi", "created_at": "2026-01-01T00:00:00Z"}
        )
        self.assertFalse(payload["is_repost"])
        self.assertFalse(payload["is_quote"])

    def test_repost_is_detected(self):
        payload = OfficialXProvider.normalize_post(
            {"id": "1", "text": "rt", "referenced_tweets": [{"type": "reposted", "id": "99"}]}
        )
        self.assertTrue(payload["is_repost"])
        self.assertFalse(payload["is_quote"])

    def test_quote_is_detected(self):
        payload = OfficialXProvider.normalize_post(
            {"id": "1", "text": "qt", "referenced_tweets": [{"type": "quoted", "id": "99"}]}
        )
        self.assertTrue(payload["is_quote"])
        self.assertFalse(payload["is_repost"])

    def test_in_reply_is_not_treated_as_a_repost(self):
        # A reply is the creator's own words; it is not amplification.
        payload = OfficialXProvider.normalize_post(
            {
                "id": "1",
                "text": "reply",
                "referenced_tweets": [{"type": "replied_to", "id": "99"}],
            }
        )
        self.assertFalse(payload["is_repost"])
        self.assertFalse(payload["is_quote"])


class FixedRewardOnlyTests(TestCase):
    def setUp(self):
        self.user, self.profile = make_user()

    def _payload(self, **overrides):
        now = timezone.now()
        payload = {
            "name": "Test",
            "slug": "test-fixed",
            "project_name": "Project",
            "token_symbol": "RHC",
            "chain_id": 1,
            "budget": "1000",
            "reward_model": RewardModel.FIXED,
            "reward_rate": "5",
            "start_at": (now - timedelta(days=1)).isoformat(),
            "end_at": (now + timedelta(days=30)).isoformat(),
        }
        payload.update(overrides)
        return payload

    def test_fixed_model_is_accepted(self):
        serializer = CampaignSerializer(data=self._payload())
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_impression_based_is_rejected(self):
        serializer = CampaignSerializer(
            data=self._payload(reward_model=RewardModel.IMPRESSION_BASED)
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("reward_model", serializer.errors)

    def test_engagement_based_is_rejected(self):
        serializer = CampaignSerializer(
            data=self._payload(reward_model=RewardModel.ENGAGEMENT_BASED)
        )
        self.assertFalse(serializer.is_valid())

    def test_hybrid_is_rejected(self):
        serializer = CampaignSerializer(data=self._payload(reward_model=RewardModel.HYBRID))
        self.assertFalse(serializer.is_valid())

    def test_zero_fixed_rate_is_rejected(self):
        serializer = CampaignSerializer(data=self._payload(reward_rate="0"))
        self.assertFalse(serializer.is_valid())
        self.assertIn("reward_rate", serializer.errors)

    def test_fixed_reward_ignores_impressions(self):
        # The whole point: reach must not change the payout.
        campaign = make_campaign(reward_model=RewardModel.FIXED, reward_rate=Decimal("5"))
        post = make_verified_post(self.profile, campaign, external_id="imm-1")
        post.impressions = 10_000_000
        high = compute_raw_reward(campaign, post)
        post.impressions = 0
        low = compute_raw_reward(campaign, post)
        self.assertEqual(high.final_amount, low.final_amount)
        self.assertEqual(high.final_amount, Decimal("5"))

