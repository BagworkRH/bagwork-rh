"""Reward calculation tests (Spec 03: reproducible, capped, deterministic)."""
from decimal import Decimal

from django.test import TestCase

from apps.campaigns.models import RewardModel
from apps.rewards.services import calculate_reward, compute_raw_reward

from .helpers import make_campaign, make_user, make_verified_post


class RewardCalculationTests(TestCase):
    def test_identical_inputs_produce_identical_output(self):
        _, profile = make_user()
        campaign = make_campaign(
            reward_model=RewardModel.IMPRESSION_BASED,
            reward_rate=Decimal("2"),
        )
        post = make_verified_post(profile, campaign, external_id="r1", text="#test")
        snapshot = {"impressions": 5000, "likes": 0, "reposts": 0, "replies": 0}

        r1 = compute_raw_reward(campaign, post, snapshot)
        r2 = compute_raw_reward(campaign, post, snapshot)
        self.assertEqual(r1.gross, Decimal("10.000000000000000000"))
        self.assertEqual(r2.gross, r1.gross)
        self.assertEqual(r1.calculation_version, r2.calculation_version)
        self.assertTrue(r1.explanation)

    def test_fixed_reward(self):
        _, profile = make_user()
        campaign = make_campaign(reward_model=RewardModel.FIXED, reward_rate=Decimal("5"))
        post = make_verified_post(profile, campaign, external_id="r2")
        result = compute_raw_reward(campaign, post)
        self.assertEqual(result.gross, Decimal("5.000000000000000000"))

    def test_engagement_based_reward(self):
        _, profile = make_user()
        campaign = make_campaign(
            reward_model=RewardModel.ENGAGEMENT_BASED, reward_rate=Decimal("0.50")
        )
        post = make_verified_post(profile, campaign, external_id="r3")
        snapshot = {"impressions": 0, "likes": 120, "reposts": 60, "replies": 20}
        result = compute_raw_reward(campaign, post, snapshot)
        self.assertEqual(result.gross, Decimal("1.000000000000000000"))

    def test_hybrid_reward(self):
        _, profile = make_user()
        campaign = make_campaign(
            reward_model=RewardModel.HYBRID,
            reward_rate=Decimal("2"),
            requirements_json={"engagement_rate": "1.00"},
        )
        post = make_verified_post(profile, campaign, external_id="r4")
        snapshot = {"impressions": 0, "likes": 100, "reposts": 0, "replies": 0}
        result = compute_raw_reward(campaign, post, snapshot)
        self.assertEqual(result.gross, Decimal("3.000000000000000000"))

    def test_per_post_cap_respected(self):
        user, profile = make_user()
        campaign = make_campaign(
            reward_model=RewardModel.FIXED,
            reward_rate=Decimal("5"),
            requirements_json={"maximum_reward_per_post": "3"},
        )
        post = make_verified_post(profile, campaign, external_id="r5")
        result = calculate_reward(campaign, post, profile, user=user)
        self.assertEqual(result.amount, Decimal("3.000000000000000000"))
        self.assertEqual(result.deduction_amount, Decimal("2.000000000000000000"))