"""Brand onboarding and USDC funding.

The cases that matter most here are the ones where the platform could be made
to believe it has money it does not: a replayed deposit, a cross-brand read,
and a quote that disagrees with the contract.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.campaigns.funding import (
    DuplicateFundingError,
    confirm_funding,
    confirmed_funded_balance,
    get_or_create_brand,
    quote_campaign_cost,
    record_funding,
)
from apps.campaigns.models import BrandFunding, BrandStatus, FundingStatus
from apps.rewards.exceptions import RewardEngineError

User = get_user_model()

TX_A = "0x" + "a" * 64
TX_B = "0x" + "b" * 64
TX_C = "0x" + "c" * 64


def make_brand(email="brand@example.com", username="branduser", company="Acme Corp"):
    user = User.objects.create_user(username=username, email=email, password="Testpass123!")
    brand = get_or_create_brand(user, company_name=company, actor=user)
    return user, brand


def authed(user):
    client = APIClient()
    token, _ = Token.objects.get_or_create(user=user)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client



class FundingServiceTests(TestCase):
    def test_deposit_starts_pending_and_does_not_count_as_funded(self):
        _, brand = make_brand()
        dep = record_funding(brand, amount="100", chain_id=46630, tx_hash=TX_A)
        # Recording is not crediting: an unverified transfer is not money yet.
        self.assertEqual(dep.status, FundingStatus.PENDING)
        self.assertEqual(confirmed_funded_balance(brand), Decimal("0"))

        confirm_funding(dep)
        self.assertEqual(confirmed_funded_balance(brand), Decimal("100"))

    def test_same_transaction_cannot_be_recorded_twice(self):
        """The replay guard: one on-chain transfer, one credit.

        A brand that could resubmit the same deposit would inflate its balance
        and let the platform promise payouts it cannot pay.
        """
        _, brand = make_brand()
        record_funding(brand, amount="100", chain_id=46630, tx_hash=TX_A)
        with self.assertRaises(DuplicateFundingError):
            record_funding(brand, amount="100", chain_id=46630, tx_hash=TX_A)
        self.assertEqual(BrandFunding.objects.filter(tx_hash=TX_A).count(), 1)

    def test_database_constraint_blocks_a_replay_even_if_the_check_is_bypassed(self):
        """Defence in depth: the constraint, not just the service, is the guard.

        If someone later adds another code path that creates a BrandFunding, the
        unique constraint still makes double-crediting impossible.
        """
        _, brand = make_brand()
        BrandFunding.objects.create(
            brand=brand,
            amount=Decimal("100"),
            chain_id=46630,
            tx_hash=TX_B,
            status=FundingStatus.CONFIRMED,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BrandFunding.objects.create(
                    brand=brand,
                    amount=Decimal("100"),
                    chain_id=46630,
                    tx_hash=TX_B,
                    status=FundingStatus.CONFIRMED,
                )

    def test_same_tx_on_a_different_chain_is_a_different_transfer(self):
        # The constraint is per (chain, tx): the same hash on another chain is
        # not the same transfer, so it is allowed.
        _, brand = make_brand()
        record_funding(brand, amount="10", chain_id=46630, tx_hash=TX_C)
        record_funding(brand, amount="10", chain_id=4663, tx_hash=TX_C)
        self.assertEqual(BrandFunding.objects.filter(tx_hash=TX_C).count(), 2)

    def test_rejects_malformed_hash_and_non_positive_amount(self):
        _, brand = make_brand()
        with self.assertRaises(RewardEngineError):
            record_funding(brand, amount="10", chain_id=46630, tx_hash="not-a-hash")
        with self.assertRaises(RewardEngineError):
            record_funding(brand, amount="0", chain_id=46630, tx_hash=TX_A)
        with self.assertRaises(RewardEngineError):
            record_funding(brand, amount="-5", chain_id=46630, tx_hash=TX_A)

    def test_suspended_brand_cannot_be_funded(self):
        _, brand = make_brand()
        brand.status = BrandStatus.SUSPENDED
        brand.save(update_fields=["status"])
        with self.assertRaises(RewardEngineError):
            record_funding(brand, amount="10", chain_id=46630, tx_hash=TX_A)

    def test_fee_is_charged_to_the_brand_and_never_reduces_a_payout(self):
        _, brand = make_brand()
        dep = record_funding(brand, amount="575", chain_id=46630, tx_hash=TX_A)
        confirm_funding(dep)
        quote = quote_campaign_cost(brand, payout_total=Decimal("500"))
        # 500 of payouts + 15% = 575 required; the brand funded exactly that.
        # Compared as Decimals, not strings: the fee is computed in 18-decimal
        # token units, so trailing zeros are a precision artefact rather than
        # a value worth asserting on.
        self.assertEqual(Decimal(quote["platform_fee"]), Decimal("75"))
        self.assertEqual(Decimal(quote["total_required"]), Decimal("575"))
        self.assertTrue(quote["sufficient"])
        # The payout is untouched: the fee is added, never subtracted.
        self.assertEqual(Decimal(quote["payout_total"]), Decimal("500"))

    def test_quote_reports_shortfall_when_underfunded(self):
        _, brand = make_brand()
        dep = record_funding(brand, amount="100", chain_id=46630, tx_hash=TX_A)
        confirm_funding(dep)
        quote = quote_campaign_cost(brand, payout_total=Decimal("500"))
        self.assertFalse(quote["sufficient"])
        self.assertEqual(Decimal(quote["shortfall"]), Decimal("475"))
        self.assertEqual(Decimal(quote["already_funded"]), Decimal("100"))


class BrandApiTests(TestCase):
    def test_endpoints_require_authentication(self):
        self.assertEqual(APIClient().get("/api/v1/brand/profile/").status_code, 401)

    def test_brand_can_create_then_read_their_profile(self):
        user, _ = make_brand()
        client = authed(user)
        response = client.get("/api/v1/brand/profile/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["company_name"], "Acme Corp")
        self.assertEqual(response.data["funded_balance"], "0")

    def test_profile_creation_is_idempotent(self):
        user, brand = make_brand()
        response = authed(user).post(
            "/api/v1/brand/profile/", {"company_name": "Different Name"}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        # The original profile is returned, not a second one.
        self.assertEqual(response.data["id"], brand.pk)
        self.assertEqual(brand.__class__.objects.filter(user=user).count(), 1)

    def test_brand_cannot_self_activate(self):
        user, brand = make_brand()
        response = authed(user).post(
            "/api/v1/brand/profile/",
            {"company_name": "Acme Corp", "status": "ACTIVE"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        brand.refresh_from_db()
        # Activation is a staff decision, not a self-service field.
        self.assertNotEqual(brand.status, BrandStatus.ACTIVE)

    def test_recording_a_deposit_does_not_credit_the_balance(self):
        user, _ = make_brand()
        client = authed(user)
        response = client.post(
            "/api/v1/brand/funding/",
            {"amount": "100", "chain_id": 46630, "tx_hash": TX_A},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], FundingStatus.PENDING)

        balance = client.get("/api/v1/brand/funding/").data["confirmed_balance"]
        self.assertEqual(Decimal(balance), Decimal("0"))

    def test_confirming_a_deposit_credits_the_balance(self):
        user, _ = make_brand()
        client = authed(user)
        created = client.post(
            "/api/v1/brand/funding/",
            {"amount": "100", "chain_id": 46630, "tx_hash": TX_A},
            format="json",
        )
        response = client.post(f"/api/v1/brand/funding/{created.data['id']}/confirm/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], FundingStatus.CONFIRMED)
        balance = client.get("/api/v1/brand/funding/").data["confirmed_balance"]
        self.assertEqual(Decimal(balance), Decimal("100"))

    def test_replay_over_http_is_rejected(self):
        user, _ = make_brand()
        client = authed(user)
        payload = {"amount": "100", "chain_id": 46630, "tx_hash": TX_A}
        self.assertEqual(client.post("/api/v1/brand/funding/", payload, format="json").status_code, 201)
        replay = client.post("/api/v1/brand/funding/", payload, format="json")
        self.assertEqual(replay.status_code, 400)
        self.assertIn("already", str(replay.data["detail"]).lower())

    def test_one_brand_cannot_confirm_another_brands_deposit(self):
        user_a, _ = make_brand(email="a@example.com", username="auser")
        user_b, _ = make_brand(email="b@example.com", username="buser")
        created = authed(user_a).post(
            "/api/v1/brand/funding/",
            {"amount": "100", "chain_id": 46630, "tx_hash": TX_A},
            format="json",
        )
        # B guessing the id must not be able to credit A's money.
        response = authed(user_b).post(
            f"/api/v1/brand/funding/{created.data['id']}/confirm/", {}, format="json"
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            BrandFunding.objects.get(pk=created.data["id"]).status, FundingStatus.PENDING
        )

    def test_one_brand_cannot_see_another_brands_funding(self):
        user_a, _ = make_brand(email="a@example.com", username="auser")
        user_b, _ = make_brand(email="b@example.com", username="buser")
        authed(user_a).post(
            "/api/v1/brand/funding/",
            {"amount": "999", "chain_id": 46630, "tx_hash": TX_B},
            format="json",
        )
        seen = authed(user_b).get("/api/v1/brand/funding/").data["fundings"]
        self.assertEqual(seen, [])
        balance = authed(user_b).get("/api/v1/brand/funding/").data["confirmed_balance"]
        self.assertEqual(Decimal(balance), Decimal("0"))

    def test_quote_endpoint_matches_the_fee_arithmetic(self):
        user, _ = make_brand()
        response = authed(user).post("/api/v1/brand/quote/", {"payout_total": "500"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["platform_fee_bps"], 1500)
        self.assertEqual(Decimal(response.data["platform_fee"]), Decimal("75"))
        self.assertEqual(Decimal(response.data["total_required"]), Decimal("575"))

    def test_quote_rejects_non_numeric_input(self):
        user, _ = make_brand()
        response = authed(user).post("/api/v1/brand/quote/", {"payout_total": "lots"}, format="json")
        self.assertEqual(response.status_code, 400)

