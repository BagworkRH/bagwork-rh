"""Claim authorization tests (Spec 04).

Covers the server side of the claim flow: the signed EIP-712 authorization the
seller's wallet submits, the calldata the contract executes, and the guard
rails (token allowlist, token decimals, signer configuration).
"""
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.blockchain import services as chain
from apps.rewards.services import approve_reward, calculate_reward, make_available
from apps.wallets.models import ClaimStatus
from apps.wallets.services import create_claim

from .helpers import (
    make_campaign,
    make_token_config,
    make_user,
    make_verified_post,
    make_verified_wallet,
    signer_address,
    signer_settings,
)

WALLET = "0x1111111111111111111111111111111111111111"
CONTRACT = "0x00000000000000000000000000000000000000BB"
TOKEN = "0x00000000000000000000000000000000000000AA"


def setup_available_reward(email="seller@example.com", username="seller", external_id="auth-1"):
    user, profile = make_user(email=email, username=username)
    campaign = make_campaign(budget=Decimal("100"), reward_rate=Decimal("5"))
    post = make_verified_post(profile, campaign, external_id=external_id)
    reward = calculate_reward(campaign, post, profile, user=user)
    approve_reward(reward, actor=user)
    make_available(reward, actor=user)
    reward.refresh_from_db()
    return user, profile, reward


class ClaimAuthorizationServiceTests(TestCase):
    @signer_settings(contract_address=CONTRACT)
    def test_authorization_payload_is_signed_and_verifiable(self):
        make_token_config(symbol="TST", address=TOKEN)
        user, profile, reward = setup_available_reward()
        wallet = make_verified_wallet(profile, address=WALLET)

        claim = create_claim(profile, wallet, reward, actor=user)
        payload = chain.get_claim_authorization_payload(claim)

        self.assertEqual(payload["wallet"], WALLET)
        self.assertEqual(payload["reward_id"], reward.pk)
        self.assertEqual(payload["chain_id"], 11155111)
        self.assertEqual(payload["contract_address"], CONTRACT)
        self.assertEqual(payload["signer_address"], signer_address())
        self.assertTrue(payload["signature"].startswith("0x"))
        self.assertTrue(chain.verify_authorization(claim, payload["signature"]))
        self.assertEqual(payload["transaction"]["to"], CONTRACT)
        self.assertEqual(payload["transaction"]["data"][:10], "0xedc19c89")

    @signer_settings(contract_address=CONTRACT)
    def test_authorization_moves_claim_to_signing(self):
        make_token_config(symbol="TST", address=TOKEN)
        user, profile, reward = setup_available_reward(external_id="auth-2")
        wallet = make_verified_wallet(profile, address=WALLET)

        claim = create_claim(profile, wallet, reward, actor=user)
        claim.refresh_from_db()
        self.assertEqual(claim.status, ClaimStatus.SIGNING)
        self.assertTrue(claim.signed_authorization)

    @signer_settings(contract_address=CONTRACT)
    def test_deadline_matches_claim_expiry(self):
        make_token_config(symbol="TST", address=TOKEN)
        user, profile, reward = setup_available_reward(external_id="auth-3")
        wallet = make_verified_wallet(profile, address=WALLET)
        claim = create_claim(profile, wallet, reward, actor=user)

        payload = chain.get_claim_authorization_payload(claim)
        self.assertEqual(payload["deadline"], int(claim.expired_at.timestamp()))

    def test_authorization_requires_configured_contract(self):
        user, profile, reward = setup_available_reward(external_id="auth-4")
        wallet = make_verified_wallet(profile, address=WALLET)
        claim = create_claim(profile, wallet, reward, actor=user)
        with self.assertRaises(chain.BlockchainError):
            chain.get_claim_authorization_payload(claim)

    @signer_settings(contract_address=CONTRACT)
    def test_token_must_be_allowlisted(self):
        user, profile, reward = setup_available_reward(external_id="auth-5")
        wallet = make_verified_wallet(profile, address=WALLET)
        claim = create_claim(profile, wallet, reward, actor=user)
        with self.assertRaises(chain.BlockchainError) as ctx:
            chain.get_claim_authorization_payload(claim)
        self.assertIn("allowlist", str(ctx.exception))

    @signer_settings(contract_address=CONTRACT)
    def test_token_decimals_are_respected(self):
        make_token_config(symbol="TST", address=TOKEN, decimals=6)
        user, profile, reward = setup_available_reward(external_id="auth-6")
        wallet = make_verified_wallet(profile, address=WALLET)
        claim = create_claim(profile, wallet, reward, actor=user)
        self.assertEqual(claim.amount_smallest_unit, 5_000_000)
class ClaimApiFlowTests(TestCase):
    """The claim flow over HTTP: create -> authorization -> submit."""

    def setUp(self):
        self.client = APIClient()

    @signer_settings(contract_address=CONTRACT)
    def test_create_claim_returns_signed_authorization(self):
        make_token_config(symbol="TST", address=TOKEN)
        user, profile, reward = setup_available_reward(external_id="flow-1")
        wallet = make_verified_wallet(profile, address=WALLET)
        self.client.force_authenticate(user=user)

        resp = self.client.post(
            "/api/v1/claims/", {"reward_id": reward.pk, "wallet_id": wallet.pk}, format="json"
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.data["authorization_ready"])
        self.assertEqual(resp.data["authorization"]["transaction"]["to"], CONTRACT)
        self.assertEqual(resp.data["status"], ClaimStatus.SIGNING)

    def test_create_claim_without_signer_still_creates_claim(self):
        user, profile, reward = setup_available_reward(external_id="flow-2")
        wallet = make_verified_wallet(profile, address=WALLET)
        self.client.force_authenticate(user=user)

        resp = self.client.post(
            "/api/v1/claims/", {"reward_id": reward.pk, "wallet_id": wallet.pk}, format="json"
        )
        self.assertEqual(resp.status_code, 201)
        self.assertFalse(resp.data["authorization_ready"])
        self.assertIn("authorization_unavailable", resp.data)

    def test_authorization_endpoint_unavailable_without_signer(self):
        user, profile, reward = setup_available_reward(external_id="flow-3")
        wallet = make_verified_wallet(profile, address=WALLET)
        claim = create_claim(profile, wallet, reward, actor=user)
        self.client.force_authenticate(user=user)

        resp = self.client.get(f"/api/v1/claims/{claim.pk}/authorization/")
        self.assertEqual(resp.status_code, 503)

    def test_authorization_endpoint_rejects_unresolvable_state(self):
        user, profile, reward = setup_available_reward(external_id="flow-4")
        wallet = make_verified_wallet(profile, address=WALLET)
        claim = create_claim(profile, wallet, reward, actor=user)
        claim.status = ClaimStatus.FAILED
        claim.save(update_fields=["status"])
        self.client.force_authenticate(user=user)

        resp = self.client.get(f"/api/v1/claims/{claim.pk}/authorization/")
        self.assertEqual(resp.status_code, 409)

    @signer_settings(contract_address=CONTRACT)
    def test_submit_records_transaction_hash(self):
        make_token_config(symbol="TST", address=TOKEN)
        user, profile, reward = setup_available_reward(external_id="flow-5")
        wallet = make_verified_wallet(profile, address=WALLET)
        claim = create_claim(profile, wallet, reward, actor=user)
        self.client.force_authenticate(user=user)

        tx_hash = "0x" + "ab" * 32
        resp = self.client.post(
            f"/api/v1/claims/{claim.pk}/submit/", {"transaction_hash": tx_hash}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], ClaimStatus.SUBMITTED)
        self.assertEqual(resp.data["transaction_hash"], tx_hash)

    @signer_settings(contract_address=CONTRACT)
    def test_submit_is_idempotent_for_same_hash(self):
        make_token_config(symbol="TST", address=TOKEN)
        user, profile, reward = setup_available_reward(external_id="flow-6")
        wallet = make_verified_wallet(profile, address=WALLET)
        claim = create_claim(profile, wallet, reward, actor=user)
        self.client.force_authenticate(user=user)

        tx_hash = "0x" + "cd" * 32
        self.client.post(
            f"/api/v1/claims/{claim.pk}/submit/", {"transaction_hash": tx_hash}, format="json"
        )
        again = self.client.post(
            f"/api/v1/claims/{claim.pk}/submit/", {"transaction_hash": tx_hash}, format="json"
        )
        self.assertEqual(again.status_code, 200)

    @signer_settings(contract_address=CONTRACT)
    def test_submit_rejects_conflicting_hash(self):
        make_token_config(symbol="TST", address=TOKEN)
        user, profile, reward = setup_available_reward(external_id="flow-7")
        wallet = make_verified_wallet(profile, address=WALLET)
        claim = create_claim(profile, wallet, reward, actor=user)
        self.client.force_authenticate(user=user)

        self.client.post(
            f"/api/v1/claims/{claim.pk}/submit/",
            {"transaction_hash": "0x" + "11" * 32},
            format="json",
        )
        conflict = self.client.post(
            f"/api/v1/claims/{claim.pk}/submit/",
            {"transaction_hash": "0x" + "22" * 32},
            format="json",
        )
        self.assertEqual(conflict.status_code, 400)

    @signer_settings(contract_address=CONTRACT)
    def test_submit_requires_hash(self):
        make_token_config(symbol="TST", address=TOKEN)
        user, profile, reward = setup_available_reward(external_id="flow-8")
        wallet = make_verified_wallet(profile, address=WALLET)
        claim = create_claim(profile, wallet, reward, actor=user)
        self.client.force_authenticate(user=user)

        resp = self.client.post(f"/api/v1/claims/{claim.pk}/submit/", {}, format="json")
        self.assertEqual(resp.status_code, 400)
