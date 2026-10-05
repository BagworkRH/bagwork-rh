"""Anti-abuse: a farm of N accounts must not earn N rewards.

These tests decide whether post-farming is actually expensive. A fixed-reward
campaign pays the same amount per verified post, so with no bound on *how many*
a creator can earn, N accounts posting N times earn N x N.

Two layers are covered, because neither is sufficient alone:

  - hard caps that make a farm unprofitable (`maximum_rewards_per_seller`, and
    a tight submission throttle)
  - cross-account signals that put the pattern in front of a human

The caps bound the loss. The signals explain it. A system with only signals
still pays out while waiting for review; a system with only caps cannot tell a
farm from a busy creator.
"""
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.audit import risk
from apps.audit.models import RiskFlag
from apps.audit.models import RiskStatus as FlagStatus
from apps.campaigns.models import CampaignStatus
from apps.rewards.exceptions import RewardEngineError
from apps.rewards.models import RewardStatus
from apps.rewards.services import calculate_reward
from apps.social.models import PostVerificationStatus, SocialPost
from apps.social.tasks import flag_suspicious_activity

from .helpers import make_campaign, make_user, make_verified_post, make_verified_wallet

CAMPAIGN_TEXT = (
    "Check out our new launch, link in bio, use code BAGWORK for ten percent off"
)


class FarmedRewardCeilingTests(TestCase):
    """`maximum_rewards_per_seller` is a promise the engine was not keeping.

    The field was validated at campaign creation and exposed in serializers,
    but nothing in the reward path read it. A brand that set "3 rewards per
    creator" was paying an unlimited number of them.
    """

    def setUp(self):
        _, self.profile = make_user("farmer@example.com", "farmer")
        self.campaign = make_campaign(
            reward_rate=Decimal("5"),
            budget=Decimal("1000"),
            maximum_rewards_per_seller=3,
        )

    def _earn(self, index, profile=None):
        profile = profile or self.profile
        post = make_verified_post(profile, self.campaign, external_id=str(index))
        return calculate_reward(self.campaign, post, profile)

    def test_a_zero_cap_means_unbounded(self):
        """Unset must stay unlimited, or every existing campaign silently breaks."""
        self.campaign.maximum_rewards_per_seller = 0
        self.campaign.save(update_fields=["maximum_rewards_per_seller"])
        for i in range(6):
            self._earn(i)
        self.assertEqual(self.profile.rewards.filter(campaign=self.campaign).count(), 6)

    def test_a_seller_stops_earning_at_the_cap(self):
        for i in range(3):
            self._earn(i)
        with self.assertRaises(RewardEngineError) as ctx:
            self._earn(3)
        self.assertIn("limit of 3", str(ctx.exception))
        self.assertEqual(self.profile.rewards.filter(campaign=self.campaign).count(), 3)

    def test_the_cap_is_per_seller_not_global(self):
        """One seller hitting their ceiling must not lock out everyone else."""
        for i in range(3):
            self._earn(i)
        _, other = make_user("clean@example.com", "clean")
        reward = self._earn("clean-1", profile=other)
        self.assertEqual(reward.amount, Decimal("5"))

    def test_a_farm_of_n_accounts_earns_n_times_the_cap_not_n_squared(self):
        """The property that matters, stated as arithmetic.

        5 accounts x 10 posts each is 50 submissions. With a cap of 3 the farm
        earns 15 rather than 50: payout is bounded per account, so extra
        accounts buy nothing without also raising the cap the brand set.
        """
        self.campaign.budget = Decimal("10000")
        self.campaign.remaining_budget = Decimal("10000")
        self.campaign.save(update_fields=["budget", "remaining_budget", "updated_at"])

        accounts, posts_each = 5, 10
        earned = 0
        for a in range(accounts):
            _, profile = make_user(f"farma{a}@example.com", f"farma{a}")
            for p in range(posts_each):
                try:
                    self._earn(f"a{a}-p{p}", profile=profile)
                except RewardEngineError:
                    continue
                earned += 1

        self.assertEqual(earned, accounts * 3)
        # Stated explicitly: the farm earned far less than one reward per post.
        self.assertLess(earned, accounts * posts_each)

    def test_a_reversed_reward_frees_the_slot(self):
        """Reversal must not lock a seller out permanently.

        REVERSED is deliberately outside the counted statuses: the brand's money
        came back, so its promise of another reward is still outstanding.
        """
        for i in range(3):
            self._earn(i)
        first = self.profile.rewards.filter(campaign=self.campaign).first()
        first.status = RewardStatus.REVERSED
        first.save(update_fields=["status"])

        reward = self._earn("after-reversal")
        self.assertEqual(reward.amount, Decimal("5"))
class SubmissionThrottleTests(TestCase):
    """A burst of submissions is the shape of a farming script.

    The global user rate is 1000/hour — a scraping guard, not an anti-abuse
    control, since it does nothing about one host submitting in a loop. A
    creator submitting by hand never approaches 20/hour.

    Rates are shrunk through `override_settings` on the whole REST_FRAMEWORK
    dict rather than replaced: the path-scoped throttles resolve their rate from
    `api_settings` per request, while DRF captured `APIView.throttle_classes` at
    import time. Replacing the dict would drop the `admin`/`auth`/`wallet` rates
    that those already-captured classes still need, and they would raise
    ImproperlyConfigured on the very first request.
    """

    def setUp(self):
        cache.clear()
        self.user, self.profile = make_user("submitter@example.com", "submitter")
        token, _ = Token.objects.get_or_create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        self.campaign = make_campaign(status=CampaignStatus.ACTIVE)

    def tearDown(self):
        cache.clear()

    def _rates(self):
        rest_framework = {
            **settings.REST_FRAMEWORK,
            "DEFAULT_THROTTLE_RATES": {
                **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
                "submit": "3/hour",
            },
        }
        return override_settings(REST_FRAMEWORK=rest_framework)

    def _submit(self, index):
        return self.client.post(
            "/api/v1/posts/submit/",
            {
                "platform": "X",
                "external_post_id": str(9000 + index),
                "campaign": self.campaign.slug,
                "text": CAMPAIGN_TEXT,
            },
            format="json",
        )

    def test_a_burst_of_submissions_is_throttled(self):
        with self._rates():
            statuses = [self._submit(i).status_code for i in range(5)]
        self.assertIn(429, statuses)
        # Only the requests that got through created posts.
        self.assertLessEqual(SocialPost.objects.count(), 3)

    def test_reads_are_not_throttled(self):
        """Only submission is limited; browsing must never be."""
        with self._rates():
            for _ in range(6):
                resp = self.client.get("/api/v1/posts/")
                self.assertNotEqual(resp.status_code, 429, resp.content)

class CrossAccountFarmSignalTests(TestCase):
    """Signals that only exist once you look across sellers.

    Every per-post signal in `collect_post_signals` is scoped to one seller,
    which is why they miss a farm: from inside one account, a farm looks like an
    ordinary prolific creator.
    """

    def setUp(self):
        _, self.profile = make_user("solo@example.com", "solo")
        self.campaign = make_campaign(status=CampaignStatus.ACTIVE)

    def test_one_seller_repeating_themselves_is_not_a_farm_signal(self):
        """One creator repeating is a different problem, already covered elsewhere."""
        post = make_verified_post(
            self.profile, self.campaign, external_id="a1", text=CAMPAIGN_TEXT
        )
        make_verified_post(
            self.profile, self.campaign, external_id="a2", text=CAMPAIGN_TEXT
        )
        names = {s["signal"] for s in risk.collect_farm_signals(post)}
        self.assertNotIn("duplicate_text", names)

    def test_identical_text_from_several_sellers_raises_a_farm_signal(self):
        post = make_verified_post(
            self.profile, self.campaign, external_id="s1", text=CAMPAIGN_TEXT
        )
        for i in range(2):
            _, peer = make_user(f"peer{i}@example.com", f"peer{i}")
            make_verified_post(
                peer, self.campaign, external_id=f"s{i + 2}", text=CAMPAIGN_TEXT
            )

        found = [
            s for s in risk.collect_farm_signals(post) if s["signal"] == "duplicate_text"
        ]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["detail"]["scope"], "cross_account")

    def test_short_shared_text_does_not_trigger_the_signal(self):
        """A bare hashtag is not evidence; the text must be a real campaign asset."""
        post = make_verified_post(self.profile, self.campaign, external_id="h1", text="#")
        for i in range(3):
            _, peer = make_user(f"tag{i}@example.com", f"tag{i}")
            make_verified_post(peer, self.campaign, external_id=f"h{i + 2}", text="#")
        self.assertEqual(risk.collect_farm_signals(post), [])

    def test_one_wallet_behind_several_sellers_raises_a_reuse_signal(self):
        """The strongest signal available: one address collecting several payouts."""
        shared = "0x" + "ab" * 20
        make_verified_wallet(self.profile, address=shared)
        post = make_verified_post(self.profile, self.campaign, external_id="w1")

        _, twin = make_user("twin@example.com", "twin")
        make_verified_wallet(twin, address=shared)

        names = {s["signal"] for s in risk.collect_farm_signals(post)}
        self.assertIn("wallet_reused_across_sellers", names)

    def test_a_farm_signal_queues_review_without_touching_the_post(self):
        """Advisory only: a flag appears, and no post or reward changes state."""
        post = make_verified_post(
            self.profile, self.campaign, external_id="q1", text=CAMPAIGN_TEXT
        )
        for i in range(2):
            _, clone = make_user(f"clone{i}@example.com", f"clone{i}")
            make_verified_post(
                clone, self.campaign, external_id=f"q{i + 2}", text=CAMPAIGN_TEXT
            )

        flag = risk.evaluate_post(post)
        self.assertIsNotNone(flag)
        self.assertEqual(flag.status, FlagStatus.OPEN)
        self.assertIn(
            "duplicate_text", [s["signal"] for s in flag.signals]
        )

        post.refresh_from_db()
        self.assertEqual(post.verification_status, PostVerificationStatus.VERIFIED)
        self.assertEqual(self.profile.rewards.count(), 0)

    def test_the_scheduled_task_surfaces_a_farm_end_to_end(self):
        """The signal must be reachable from the task, not only from tests.

        `evaluate_post` was correct in isolation while `flag_suspicious_activity`
        only ran the per-post signals, so the cross-account check existed but was
        never invoked in production. This asserts the wiring, not the detector.
        """
        post = make_verified_post(
            self.profile, self.campaign, external_id="t1", text=CAMPAIGN_TEXT
        )
        for i in range(2):
            _, clone = make_user(f"task{i}@example.com", f"task{i}")
            make_verified_post(
                clone, self.campaign, external_id=f"t{i + 2}", text=CAMPAIGN_TEXT
            )

        result = flag_suspicious_activity(hours=24)
        self.assertGreaterEqual(result["checked"], 1)

        flag = RiskFlag.objects.filter(subject_id=post.pk).first()
        self.assertIsNotNone(flag, "the farm pattern never reached the review queue")
        names = [s["signal"] for s in flag.signals]
        self.assertIn("duplicate_text", names)

    def test_a_legitimate_creator_raises_no_flag(self):
        """The false-positive check matters more than the detection rate."""
        post = make_verified_post(self.profile, self.campaign, external_id="legit")
        make_verified_wallet(self.profile, address="0x" + "cd" * 20)
        self.assertIsNone(risk.evaluate_post(post))
        self.assertEqual(RiskFlag.objects.count(), 0)
