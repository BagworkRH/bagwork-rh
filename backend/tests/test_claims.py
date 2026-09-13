"""Claim idempotency and permission tests (Spec 03 & 04)."""
from decimal import Decimal

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.rewards.exceptions import RewardEngineError
from apps.rewards.services import approve_reward, calculate_reward, make_available
from apps.wallets.models import ClaimStatus, Wallet
from apps.wallets.services import create_claim

from .helpers import make_campaign, make_user, make_verified_post


def setup_available_reward():
    user, profile = make_user()
    campaign = make_campaign(budget=Decimal("100"), reward_rate=Decimal("5"))
    post = make_verified_post(profile, campaign, external_id="claim-1")
    reward = calculate_reward(campaign, post, profile, user=user)
    approve_reward(reward, actor=user)
    make_available(reward, actor=user)
    reward.refresh_from_db()  # status transitions happen on locked instances
    return user, profile, reward


class ClaimServicesTests(TestCase):
    def test_claim_requires_verified_wallet(self):
        user, profile, reward = setup_available_reward()
        wallet = Wallet.objects.create(
            seller=profile,
            address="0x1111111111111111111111111111111111111111",
            chain_id=11155111,
            verified=False,
        )
        with self.assertRaises(RewardEngineError):
            create_claim(profile, wallet, reward, actor=user)

    def test_claim_requires_available_reward(self):
        user, profile = make_user()
        campaign = make_campaign(budget=Decimal("100"), reward_rate=Decimal("5"))
        post = make_verified_post(profile, campaign, external_id="claim-2")
        reward = calculate_reward(campaign, post, profile, user=user)
        wallet = Wallet.objects.create(
            seller=profile,
            address="0x2222222222222222222222222222222222222222",
            chain_id=11155111,
            verified=True,
        )
        with self.assertRaises(RewardEngineError):
            create_claim(profile, wallet, reward, actor=user)

    def test_duplicate_claim_rejected(self):
        user, profile, reward = setup_available_reward()
        wallet = Wallet.objects.create(
            seller=profile,
            address="0x3333333333333333333333333333333333333333",
            chain_id=11155111,
            verified=True,
        )
        claim = create_claim(profile, wallet, reward, actor=user)
        self.assertEqual(claim.status, ClaimStatus.CREATED)
        with self.assertRaises(RewardEngineError):
            create_claim(profile, wallet, reward, actor=user)

    def test_claim_amount_matches_reward(self):
        user, profile, reward = setup_available_reward()
        wallet = Wallet.objects.create(
            seller=profile,
            address="0x4444444444444444444444444444444444444444",
            chain_id=11155111,
            verified=True,
        )
        claim = create_claim(profile, wallet, reward, actor=user)
        self.assertEqual(claim.amount, Decimal("5.000000000000000000"))
        self.assertEqual(claim.amount_smallest_unit, 5_000_000_000_000_000_000)
        self.assertIsNotNone(claim.nonce)


class ClaimApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_create_claim_via_api_requires_wallet(self):
        user, profile, reward = setup_available_reward()
        self.client.force_authenticate(user=user)
        resp = self.client.post(
            "/api/v1/claims/",
            {"reward_id": reward.pk, "wallet_id": 999999},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_permission_boundary_seller_cannot_see_others_claims(self):
        user_a, profile_a, reward = setup_available_reward()
        user_b, profile_b = make_user(email="other@example.com", username="other")
        wallet = Wallet.objects.create(
            seller=profile_a,
            address="0x5555555555555555555555555555555555555555",
            chain_id=11155111,
            verified=True,
        )
        claim = create_claim(profile_a, wallet, reward, actor=user_a)
        self.client.force_authenticate(user=user_b)
        resp = self.client.get(f"/api/v1/claims/{claim.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)