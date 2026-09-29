"""Fraud/risk review-queue tests (Spec 03 anti-fraud, Spec 05 Phase 7).

The rule under test: signals produce a score and a *queue entry* — never an
automatic accusation — and only a human decision resolves a flag.
"""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.audit import risk
from apps.audit.models import AuditLog, RiskFlag, RiskStatus, RiskSubjectType
from apps.blockchain import services as chain
from apps.rewards.exceptions import RewardEngineError
from apps.rewards.services import approve_reward, calculate_reward, make_available
from apps.social.models import (
    OriginalityEvidence,
    PostMetricSnapshot,
    PostVerificationStatus,
    SocialPost,
)
from apps.social.tasks import flag_suspicious_activity
from apps.wallets.models import ClaimStatus
from apps.wallets.services import create_claim

from .helpers import make_campaign, make_token_config, make_user, make_verified_wallet

WALLET = "0x1111111111111111111111111111111111111111"


def make_post(profile, campaign, external_id, **kwargs):
    defaults = {
        "account": None,
        "external_post_id": external_id,
        "seller": profile,
        "campaign": campaign,
        "post_url": f"https://x.com/status/{external_id}",
        "text_snapshot": kwargs.pop("text", f"promo {external_id}"),
        "published_at": kwargs.pop("published_at", timezone.now()),
        "verification_status": kwargs.pop(
            "verification_status", PostVerificationStatus.VERIFIED
        ),
        # A reward is only payable when the platform confirmed originality.
        "originality_evidence": kwargs.pop(
            "originality_evidence", OriginalityEvidence.PROVIDER_CONFIRMED
        ),
    }
    defaults.update(kwargs)
    return SocialPost.objects.create(**defaults)


def add_snapshots(post, first, second):
    """Two metric snapshots: (likes, reposts, replies) tuples."""
    now = timezone.now()
    for offset, values in ((2, first), (1, second)):
        likes, reposts, replies = values
        PostMetricSnapshot.objects.create(
            post=post,
            collected_at=now - timedelta(hours=offset),
            impressions=0,
            likes=likes,
            reposts=reposts,
            replies=replies,
        )


class ScoringTests(TestCase):
    def test_weak_evidence_never_enters_the_queue(self):
        """A single ordinary post produces no flag at all (Spec 03)."""
        _, profile = make_user()
        campaign = make_campaign()
        post = make_post(profile, campaign, "weak-1", text="a normal campaign post")

        self.assertIsNone(risk.evaluate_post(post))
        self.assertEqual(RiskFlag.objects.count(), 0)

    def test_engagement_spike_is_queued_with_evidence(self):
        _, profile = make_user()
        campaign = make_campaign()
        post = make_post(profile, campaign, "spike-1")
        add_snapshots(post, first=(10, 1, 0), second=(1200, 400, 60))

        flag = risk.evaluate_post(post)
        self.assertIsNotNone(flag)
        self.assertEqual(flag.subject_type, RiskSubjectType.POST)
        self.assertEqual(flag.subject_id, post.pk)
        self.assertEqual(flag.seller, profile)
        self.assertEqual(flag.status, RiskStatus.OPEN)
        self.assertIn("engagement_spike", [s["signal"] for s in flag.signals])
        self.assertGreaterEqual(flag.score, risk.review_threshold())

    def test_duplicate_text_is_a_signal(self):
        _, profile = make_user()
        campaign = make_campaign()
        text = "Buy $TST today and join the campaign #TST now"
        make_post(profile, campaign, "dup-a", text=text)
        second = make_post(profile, campaign, "dup-b", text=text)
        make_post(profile, campaign, "dup-c", text=text)

        signals = risk.collect_post_signals(second)
        self.assertIn("duplicate_text", [s["signal"] for s in signals])

    def test_excessive_posting_frequency_is_a_signal(self):
        _, profile = make_user()
        campaign = make_campaign()
        now = timezone.now()
        for index in range(risk.POSTS_PER_DAY_THRESHOLD):
            make_post(
                profile,
                campaign,
                f"freq-{index}",
                published_at=now - timedelta(minutes=index + 1),
            )
        last = make_post(profile, campaign, "freq-last", published_at=now)

        signals = risk.collect_post_signals(last)
        self.assertIn("excessive_posting_frequency", [s["signal"] for s in signals])

    def test_bot_like_engagement_ratio_is_a_signal(self):
        _, profile = make_user()
        campaign = make_campaign()
        post = make_post(profile, campaign, "bot-1")
        SocialPost.objects.filter(pk=post.pk).update(
            impressions=10000, likes=3000, total_engagement=3000
        )
        post.refresh_from_db()

        signals = risk.collect_post_signals(post)
        self.assertIn("bot_like_engagement_ratio", [s["signal"] for s in signals])

    def test_scoring_never_mutates_the_post(self):
        _, profile = make_user()
        campaign = make_campaign()
        post = make_post(profile, campaign, "readonly-1")
        add_snapshots(post, first=(10, 1, 0), second=(1200, 400, 60))
        before = SocialPost.objects.get(pk=post.pk).verification_status

        risk.evaluate_post(post)
        self.assertEqual(SocialPost.objects.get(pk=post.pk).verification_status, before)


class QueueBehaviourTests(TestCase):
    def test_rescoring_updates_the_single_open_flag(self):
        _, profile = make_user()
        campaign = make_campaign()
        post = make_post(profile, campaign, "queue-1")
        add_snapshots(post, first=(10, 1, 0), second=(1200, 400, 60))

        first = risk.evaluate_post(post)
        second = risk.evaluate_post(post)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(RiskFlag.objects.filter(subject_id=post.pk).count(), 1)

    def test_reviewer_dismissal_is_audited(self):
        _, profile = make_user()
        campaign = make_campaign()
        post = make_post(profile, campaign, "queue-2")
        add_snapshots(post, first=(10, 1, 0), second=(1200, 400, 60))
        flag = risk.evaluate_post(post)
        reviewer = make_user(email="review@example.com", username="reviewer")[0]

        flag = risk.resolve_flag(flag, "dismiss", "Normal growth.", actor=reviewer)
        self.assertEqual(flag.status, RiskStatus.DISMISSED)
        self.assertEqual(flag.resolved_by, reviewer)
        self.assertIsNotNone(flag.resolved_at)
        self.assertTrue(
            AuditLog.objects.filter(action="RISK_FLAG_DISMISSED", actor=reviewer).exists()
        )

    def test_confirmed_flag_is_not_reopened_by_a_rescan(self):
        _, profile = make_user()
        campaign = make_campaign()
        post = make_post(profile, campaign, "queue-3")
        add_snapshots(post, first=(10, 1, 0), second=(1200, 400, 60))
        flag = risk.evaluate_post(post)
        risk.resolve_flag(flag, "confirm", "Fraudulent engagement.")

        new_flag = risk.evaluate_post(post)
        self.assertNotEqual(new_flag.pk, flag.pk)
        self.assertEqual(risk.open_flags().count(), 1)

    def test_resolve_rejects_unknown_decision(self):
        _, profile = make_user()
        campaign = make_campaign()
        post = make_post(profile, campaign, "queue-4")
        add_snapshots(post, first=(10, 1, 0), second=(1200, 400, 60))
        flag = risk.evaluate_post(post)

        with self.assertRaises(RewardEngineError):
            risk.resolve_flag(flag, "ban_everything")

    def test_scan_recent_posts_only_sees_recent_posts(self):
        _, profile = make_user()
        campaign = make_campaign()
        stale = make_post(
            profile, campaign, "scan-stale", published_at=timezone.now() - timedelta(days=5)
        )
        add_snapshots(stale, first=(10, 1, 0), second=(1200, 400, 60))

        result = risk.scan_recent_posts(hours=24)
        self.assertEqual(result["checked"], 0)
        self.assertEqual(result["flagged"], [])
        self.assertEqual(RiskFlag.objects.count(), 0)

    def test_wallet_reuse_across_sellers_is_queued(self):
        _, profile = make_user()
        _, other_profile = make_user(email="other@example.com", username="other")
        wallet = make_verified_wallet(profile, address=WALLET)
        make_verified_wallet(other_profile, address=WALLET)

        flag = risk.evaluate_wallet(wallet)
        self.assertIsNotNone(flag)
        self.assertEqual(flag.subject_type, RiskSubjectType.WALLET)
        self.assertIn("wallet_reused_across_sellers", [s["signal"] for s in flag.signals])

    def test_wallet_without_reuse_is_not_queued(self):
        _, profile = make_user()
        wallet = make_verified_wallet(profile, address=WALLET)
        self.assertIsNone(risk.evaluate_wallet(wallet))


class ClaimVolumeTests(TestCase):
    def setup_claim(self, external_id="risk-claim-1"):
        make_token_config(symbol="TST")
        user, profile = make_user()
        campaign = make_campaign(budget=Decimal("100"), reward_rate=Decimal("5"))
        post = make_post(profile, campaign, external_id)
        reward = calculate_reward(campaign, post, profile, user=user)
        approve_reward(reward, actor=user)
        make_available(reward, actor=user)
        reward.refresh_from_db()
        wallet = make_verified_wallet(profile, address=WALLET)
        claim = create_claim(profile, wallet, reward, actor=user)
        return user, profile, claim

    def test_high_claim_volume_is_queued_for_review(self):
        _, profile, _ = self.setup_claim()

        result = risk.evaluate_claim_volume(threshold_per_hour=1)
        self.assertEqual(result["checked"], 1)
        self.assertEqual(len(result["flagged"]), 1)

        flag = RiskFlag.objects.get(subject_type=RiskSubjectType.SELLER, subject_id=profile.pk)
        self.assertEqual(flag.status, RiskStatus.OPEN)
        self.assertIn("unusual_claim_volume", [s["signal"] for s in flag.signals])

    def test_low_claim_volume_is_not_queued(self):
        _, _, _ = self.setup_claim("risk-claim-2")

        result = risk.evaluate_claim_volume(threshold_per_hour=50)
        self.assertEqual(result["flagged"], [])
        self.assertEqual(RiskFlag.objects.count(), 0)

    def test_claim_volume_flag_does_not_block_claims(self):
        """Monitoring never enforces: the seller can keep claiming (Spec 04)."""
        user, profile, claim = self.setup_claim("risk-claim-3")
        risk.evaluate_claim_volume(threshold_per_hour=1)

        reward_two = calculate_reward(
            claim.reward.campaign,
            make_post(profile, claim.reward.campaign, "risk-claim-3b"),
            profile,
            user=user,
        )
        approve_reward(reward_two, actor=user)
        make_available(reward_two, actor=user)
        reward_two.refresh_from_db()
        second = create_claim(profile, claim.wallet, reward_two, actor=user)
        self.assertEqual(second.status, ClaimStatus.CREATED)


class TaskWiringTests(TestCase):
    def test_blockchain_monitor_delegates_to_the_queue(self):
        result = chain.monitor_claim_volume(threshold_per_hour=1)
        self.assertIn("checked", result)
        self.assertIn("flagged", result)

    def test_flag_suspicious_activity_task_scores_posts(self):
        _, profile = make_user()
        campaign = make_campaign()
        post = make_post(profile, campaign, "task-1")
        add_snapshots(post, first=(10, 1, 0), second=(1200, 400, 60))

        result = flag_suspicious_activity()
        self.assertEqual(result["checked"], 1)
        self.assertEqual(len(result["flagged"]), 1)
        self.assertEqual(risk.open_flags().count(), 1)
