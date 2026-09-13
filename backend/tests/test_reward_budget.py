"""Reward budget/lifecycle tests (Spec 03: budget safety, idempotency, audit)."""
from decimal import Decimal

from django.test import TestCase

from apps.rewards.exceptions import RewardEngineError
from apps.rewards.models import RewardStatus
from apps.rewards.services import (
    approve_reward,
    calculate_reward,
    make_available,
    reverse_reward,
)
from apps.social.models import PostVerificationStatus

from .helpers import make_campaign, make_user, make_verified_post


class RewardBudgetTests(TestCase):
    def test_budget_deducted_when_reward_created(self):
        user, profile = make_user()
        campaign = make_campaign(budget=Decimal("100"), reward_rate=Decimal("5"))
        post = make_verified_post(profile, campaign, external_id="b1")
        reward = calculate_reward(campaign, post, profile, user=user)
        campaign.refresh_from_db()
        self.assertEqual(campaign.remaining_budget, Decimal("95"))
        self.assertEqual(reward.status, RewardStatus.PENDING)

    def test_budget_cannot_become_negative(self):
        user, profile = make_user()
        campaign = make_campaign(budget=Decimal("5"), reward_rate=Decimal("10"))
        post = make_verified_post(profile, campaign, external_id="b2")
        with self.assertRaises(RewardEngineError):
            calculate_reward(campaign, post, profile, user=user)
        campaign.refresh_from_db()
        self.assertEqual(campaign.remaining_budget, Decimal("5"))

    def test_duplicate_reward_rejected(self):
        user, profile = make_user()
        campaign = make_campaign(budget=Decimal("100"), reward_rate=Decimal("5"))
        post = make_verified_post(profile, campaign, external_id="b3")
        calculate_reward(campaign, post, profile, user=user)
        with self.assertRaises(RewardEngineError):
            calculate_reward(campaign, post, profile, user=user)

    def test_unverified_post_cannot_be_rewarded(self):
        user, profile = make_user()
        campaign = make_campaign(budget=Decimal("100"), reward_rate=Decimal("5"))
        post = make_verified_post(profile, campaign, external_id="b4")
        post.verification_status = PostVerificationStatus.METRICS_PENDING
        post.save()
        with self.assertRaises(RewardEngineError):
            calculate_reward(campaign, post, profile, user=user)

    def test_reverse_restores_budget(self):
        user, profile = make_user()
        campaign = make_campaign(budget=Decimal("100"), reward_rate=Decimal("5"))
        post = make_verified_post(profile, campaign, external_id="b5")
        reward = calculate_reward(campaign, post, profile, user=user)
        reverse_reward(reward, "duplicate", actor=user)
        campaign.refresh_from_db()
        self.assertEqual(campaign.remaining_budget, Decimal("100"))
        reward.refresh_from_db()
        self.assertEqual(reward.status, RewardStatus.REVERSED)
        self.assertEqual(reward.reversal_reason, "duplicate")

    def test_per_seller_cap(self):
        user, profile = make_user()
        campaign = make_campaign(
            budget=Decimal("100"),
            reward_rate=Decimal("5"),
            maximum_reward_per_seller=Decimal("7"),
        )
        post1 = make_verified_post(profile, campaign, external_id="b6")
        post2 = make_verified_post(profile, campaign, external_id="b7")
        r1 = calculate_reward(campaign, post1, profile, user=user)
        approve_reward(r1, actor=user)
        make_available(r1, actor=user)
        r2 = calculate_reward(campaign, post2, profile, user=user)
        self.assertEqual(r2.amount, Decimal("2.000000000000000000"))


class RewardLifecycleTests(TestCase):
    def test_full_lifecycle(self):
        user, profile = make_user()
        campaign = make_campaign(budget=Decimal("100"), reward_rate=Decimal("5"))
        post = make_verified_post(profile, campaign, external_id="l1")
        reward = calculate_reward(campaign, post, profile, user=user)
        self.assertEqual(reward.status, RewardStatus.PENDING)

        approve_reward(reward, actor=user)
        reward.refresh_from_db()
        self.assertEqual(reward.status, RewardStatus.APPROVED)
        self.assertIsNotNone(reward.approved_at)

        make_available(reward, actor=user)
        reward.refresh_from_db()
        self.assertEqual(reward.status, RewardStatus.AVAILABLE)

    def test_approve_is_idempotent(self):
        user, profile = make_user()
        campaign = make_campaign(budget=Decimal("100"), reward_rate=Decimal("5"))
        post = make_verified_post(profile, campaign, external_id="l2")
        reward = calculate_reward(campaign, post, profile, user=user)
        approve_reward(reward, actor=user)
        same = approve_reward(reward, actor=user)
        self.assertEqual(same.status, RewardStatus.APPROVED)