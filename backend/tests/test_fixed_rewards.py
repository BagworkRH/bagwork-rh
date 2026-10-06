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
from apps.social.models import (
    OriginalityEvidence,
    PostVerificationStatus,
    SocialPost,
)
from apps.social.post_services import run_verification
from apps.social.providers.official import OfficialXProvider

from .helpers import make_campaign, make_user, make_verified_post


class OriginalityGateTests(TestCase):
    def setUp(self):
        self.user, self.profile = make_user()
        self.campaign = make_campaign()
        self.now = timezone.now()

    def _post(self, external_id, **kwargs):
        # A post only earns when the platform has confirmed it, so tests that
        # expect a verified post must supply that evidence rather than assume it.
        kwargs.setdefault("text_snapshot", "hello #ad")
        kwargs.setdefault("originality_evidence", OriginalityEvidence.PROVIDER_CONFIRMED)
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
            originality_evidence=OriginalityEvidence.PROVIDER_CONFIRMED,
        )
        post = run_verification(post)
        self.assertEqual(post.verification_status, PostVerificationStatus.NOT_DISCLOSED)

    def test_campaign_may_opt_into_non_original(self):
        # `allow_non_original` waives the *flag* gate only. The evidence gate
        # still requires the platform to have looked at the post -- two
        # deliberate, independent switches. A provider that has actively said
        # "this is a repost" is never overridden by this flag.
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
            originality_evidence=OriginalityEvidence.PROVIDER_CONFIRMED,
        )
        post = run_verification(post)
        self.assertEqual(post.verification_status, PostVerificationStatus.VERIFIED)

    def test_allow_non_original_does_not_override_provider_rejection(self):
        # The flag must not become a way to pay for a post the platform has
        # positively identified as a repost.
        campaign = make_campaign(
            slug="non-original-strict",
            requirements_json={"allow_non_original": True},
        )
        post = SocialPost.objects.create(
            seller=self.profile,
            campaign=campaign,
            external_post_id="rep-3",
            post_url="https://x.com/i/status/rep-3",
            text_snapshot="reposted #ad",
            published_at=self.now,
            is_repost=True,
            originality_evidence=OriginalityEvidence.PROVIDER_REJECTED,
        )
        post = run_verification(post)
        self.assertEqual(post.verification_status, PostVerificationStatus.NOT_ORIGINAL)


class FailClosedTests(TestCase):
    """A reward must never be paid on an unconfirmed originality claim.

    This is the whole point of Stage 1: if the platform is unreachable we do
    not fall back to trusting the seller. Breaking the provider must not
    produce a payout.
    """

    def setUp(self):
        self.user, self.profile = make_user()
        self.campaign = make_campaign(slug="fail-closed")
        self.now = timezone.now()

    def _post(self, external_id, evidence, **kwargs):
        kwargs.setdefault("text_snapshot", "original content #ad")
        post = SocialPost.objects.create(
            seller=self.profile,
            campaign=self.campaign,
            external_post_id=external_id,
            post_url=f"https://x.com/i/status/{external_id}",
            published_at=self.now,
            originality_evidence=evidence,
            **kwargs,
        )
        return run_verification(post)

    def test_self_reported_originality_does_not_verify(self):
        post = self._post("fc-1", OriginalityEvidence.SELF_REPORTED)
        self.assertEqual(post.verification_status, PostVerificationStatus.PROVIDER_ERROR)
        self.assertIn("not confirmed", post.rejection_reason.lower())

    def test_unavailable_provider_does_not_verify(self):
        post = self._post("fc-2", OriginalityEvidence.PROVIDER_UNAVAILABLE)
        self.assertEqual(post.verification_status, PostVerificationStatus.PROVIDER_ERROR)

    def test_provider_rejected_is_not_original(self):
        post = self._post(
            "fc-3", OriginalityEvidence.PROVIDER_REJECTED, is_repost=True
        )
        self.assertEqual(post.verification_status, PostVerificationStatus.NOT_ORIGINAL)

    def test_provider_confirmed_verifies(self):
        post = self._post("fc-4", OriginalityEvidence.PROVIDER_CONFIRMED)
        self.assertEqual(post.verification_status, PostVerificationStatus.VERIFIED)

    def test_unconfirmed_post_cannot_be_paid(self):
        # The reward layer must refuse even if a post somehow claims VERIFIED.
        from apps.rewards.exceptions import RewardEngineError  # noqa: PLC0415
        from apps.rewards.services import calculate_reward  # noqa: PLC0415

        post = SocialPost.objects.create(
            seller=self.profile,
            campaign=self.campaign,
            external_post_id="fc-5",
            post_url="https://x.com/i/status/fc-5",
            text_snapshot="#ad",
            published_at=self.now,
            originality_evidence=OriginalityEvidence.SELF_REPORTED,
            verification_status=PostVerificationStatus.VERIFIED,
        )
        with self.assertRaises(RewardEngineError):
            calculate_reward(self.campaign, post, self.profile)

    def test_campaign_may_opt_out_of_the_evidence_gate(self):
        # An explicit escape hatch, off by default, for campaigns that accept
        # self-reported originality (e.g. a private pilot).
        campaign = make_campaign(
            slug="pilot-campaign",
            requirements_json={"allow_unconfirmed_originality": True},
        )
        post = SocialPost.objects.create(
            seller=self.profile,
            campaign=campaign,
            external_post_id="fc-6",
            post_url="https://x.com/i/status/fc-6",
            text_snapshot="pilot post #ad",
            published_at=self.now,
            originality_evidence=OriginalityEvidence.SELF_REPORTED,
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
        # `retweeted` is what X actually returns (verified against the live
        # API); the fixture used to say "reposted", which X never sends, so
        # this assertion passed while every real retweet was treated as
        # original and paid.
        payload = OfficialXProvider.normalize_post(
            {"id": "1", "text": "rt", "referenced_tweets": [{"type": "retweeted", "id": "99"}]}
        )
        self.assertTrue(payload["is_repost"])
        self.assertFalse(payload["is_quote"])

    def test_live_payload_shapes_are_mapped_correctly(self):
        """Verbatim shapes captured from the live X API.

        Stage 2's point is that the documented contract and the real one are
        not the same thing. These payloads were copied from actual responses,
        so a future change to the mapping breaks here instead of at payout
        time. Note that an original post omits `referenced_tweets` entirely,
        while a retweet carries `type: "retweeted"`.
        """
        original = {
            "created_at": "2026-10-06T11:40:02.000Z",
            "edit_history_tweet_ids": ["2107435709401325699"],
            "id": "2107435709401325699",
            "text": "CoinMarketCap | RWA Stocks",
        }
        mapped = OfficialXProvider.normalize_post(original)
        self.assertFalse(mapped["is_repost"])
        self.assertFalse(mapped["is_quote"])
        self.assertEqual(mapped["created_at"], "2026-10-06T11:40:02.000+00:00")

        retweet = {
            "created_at": "2026-10-06T11:50:59.000Z",
            "edit_history_tweet_ids": ["2107435825478656295"],
            "id": "2107435825478656295",
            "text": "RT @someone: their original words",
            "referenced_tweets": [{"type": "retweeted", "id": "2107432167689384018"}],
        }
        mapped = OfficialXProvider.normalize_post(retweet)
        self.assertTrue(mapped["is_repost"])
        self.assertFalse(mapped["is_quote"])

    def test_unknown_reference_type_fails_closed(self):
        """An unrecognised type must not be assumed original.

        The gate exists to stop paying for amplification, so a type we do not
        recognise is treated as non-original rather than waved through.
        """
        payload = OfficialXProvider.normalize_post(
            {"id": "1", "text": "?", "referenced_tweets": [{"type": "some_future_type", "id": "9"}]}
        )
        self.assertTrue(payload["is_repost"])

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

