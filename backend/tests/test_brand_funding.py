"""Brand onboarding and USDG funding.

The cases that matter most here are the ones where the platform could be made
to believe it has money it does not: a replayed deposit, a cross-brand read,
a quote that disagrees with the contract, and — the one that used to be
missing entirely — a deposit that was never actually verified.
"""
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.blockchain.models import TokenConfig
from apps.blockchain.tasks import confirm_pending_fundings
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
from tests.helpers import (
    chain_showing as _chain_showing,
)
from tests.helpers import (
    make_token_config,
)

User = get_user_model()

TX_A = "0x" + "a" * 64
TX_B = "0x" + "b" * 64
TX_C = "0x" + "c" * 64

TOKEN = "USDG"
TOKEN_ADDRESS = "0x000000000000000000000000000000000000FEE1"
OTHER_TOKEN_ADDRESS = "0x000000000000000000000000000000000000BEEF"
SENDER = "0x1234567890123456789012345678901234567890"
STRANGER = "0x9999999999999999999999999999999999999999"
CHAIN = 46630
ONE = 10**18  # 1 USDG in 18-decimal base units


def allowlist_usdg(decimals=18):
    return make_token_config(
        symbol=TOKEN, chain_id=CHAIN, address=TOKEN_ADDRESS, decimals=decimals
    )


def chain_showing(**chain):
    """`helpers.chain_showing` with this module's USDG contract bound in.

    The tests below are about *one* token on *one* chain, so repeating the
    address and sender on every call would obscure the part that differs —
    which is the whole point of each test.
    """
    chain.setdefault("token_address", TOKEN_ADDRESS)
    chain.setdefault("sender", SENDER)
    return _chain_showing(**chain)


def make_brand(email="brand@example.com", username="branduser", company="Acme Corp"):
    user = User.objects.create_user(username=username, email=email, password="Testpass123!")
    brand = get_or_create_brand(user, company_name=company, actor=user)
    return user, brand


def authed(user):
    client = APIClient()
    token, _ = Token.objects.get_or_create(user=user)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client



class DepositVerificationTests(TestCase):
    """Confirming a deposit must be a question only the chain can answer.

    Every test here drives the real `verify_deposit` through a faked transport
    and asserts the *balance did not move*. The previous implementation set
    `status = CONFIRMED` unconditionally, so every one of these refusal cases
    would have failed against it — which is the point. A suite like this is
    what was missing while the funding gate was keyed on a self-issued token.
    """

    def setUp(self):
        allowlist_usdg()
        _, self.brand = make_brand()
        self.dep = record_funding(
            self.brand, amount="100", chain_id=CHAIN, tx_hash=TX_A, token_symbol=TOKEN
        )

    def rejects(self, fragment, **chain):
        """The deposit must be refused, and the message must say why.

        Asserting on the reason as well as the refusal matters: a verifier that
        raised for the wrong reason would still be failing closed, but the brand
        reading that message would be told something untrue about their deposit.
        """
        with self.assertRaises(RewardEngineError) as caught:
            with chain_showing(**chain):
                confirm_funding(self.dep)
        self.assertIn(fragment, str(caught.exception).lower())
        self.dep.refresh_from_db()
        self.assertEqual(self.dep.status, FundingStatus.PENDING)
        self.assertEqual(confirmed_funded_balance(self.brand), Decimal("0"))
        self.assertIsNone(self.dep.confirmed_at)
        # No evidence recorded, because nothing was ever verified.
        self.assertIsNone(self.dep.verified_block)

    def test_a_brand_cannot_confirm_its_own_unverified_deposit(self):
        """The original bug, restated as a test that now fails.

        Nothing was sent and no transaction exists, but the brand holds an
        authenticated session and knows its own deposit id. That combination
        used to be enough to mint a confirmed balance.
        """
        self.rejects("no receipt found", no_receipt=True)

    def test_confirming_with_no_rpc_available_does_not_credit(self):
        """An unreachable node leaves the deposit pending, never confirms it.

        The tempting behaviour during an outage is to trust the brand. That is
        precisely the outage a farming script would wait for.
        """
        self.rejects("cannot reach the chain", node=False)

    def test_a_failed_transaction_does_not_credit(self):
        """A reverted transfer emits a receipt with status 0 and moves nothing."""
        self.rejects("failed on chain", status=0)

    def test_a_transaction_that_sent_money_elsewhere_does_not_credit(self):
        """The recipient must be the platform treasury.

        Without this check a brand could make a perfectly real, correctly
        valued transfer of its own stablecoin to a wallet it controls and have
        the platform call it funding.
        """
        self.rejects("treasury", recipient=STRANGER)

    def test_a_transfer_of_a_different_token_does_not_credit(self):
        """The log must come from the allowlisted token's own contract.

        Matching the event signature alone would accept any contract emitting
        a Transfer-shaped log — a wrapper, or a scam token named to look real.
        """
        self.rejects("treasury", token_address=OTHER_TOKEN_ADDRESS)

    def test_underpayment_does_not_credit_the_claimed_amount(self):
        """A transfer of 1 USDG cannot fund a 100 USDG campaign.

        Crediting the claimed amount rather than the received one is the second
        way this function could have been exploited: the transfer is real, the
        token is correct, only the size is a lie.
        """
        self.rejects("but the deposit claims", amount_units=1 * ONE)

    def test_a_receipt_with_no_transfer_does_not_credit(self):
        """A successful transaction that moved no stablecoin is not funding."""
        self.rejects("treasury", logs=[])

    def test_a_recently_mined_transaction_does_not_credit_yet(self):
        """Zero confirmations means the chain can still take it back."""
        self.rejects("confirmation", block_number=100, head=100, confirmations=3)

    def test_the_wrong_network_does_not_credit(self):
        """A hash is not chain-qualified, so the node's own id must match."""
        self.rejects("wrong network", chain_id=4663)

    def test_a_token_that_is_not_allowlisted_does_not_credit(self):
        """Decimals come from the allowlist, so an unknown token is unverifiable."""
        TokenConfig.objects.all().delete()
        self.rejects("not on the allowlist")

    def test_a_genuine_transfer_does_credit_and_records_the_evidence(self):
        """The control: a real transfer credits, and the receipt is kept.

        Without this the whole class would pass against a verifier that
        rejects everything — safe, but useless.
        """
        with chain_showing(amount_units=100 * ONE, block_number=90, head=100):
            confirmed = confirm_funding(self.dep, actor=self.brand.user)

        confirmed.refresh_from_db()
        self.assertEqual(confirmed.status, FundingStatus.CONFIRMED)
        self.assertEqual(confirmed_funded_balance(self.brand), Decimal("100"))
        # The evidence is what makes a funding dispute answerable, so it is
        # asserted rather than assumed.
        self.assertEqual(confirmed.verified_block, 90)
        self.assertEqual(confirmed.verified_confirmations, 10)
        self.assertEqual(confirmed.verified_sender.lower(), SENDER.lower())
        self.assertEqual(confirmed.verified_amount, Decimal("100"))

    def test_overpayment_does_not_raise_the_recorded_deposit(self):
        """Sending more than claimed does not inflate the recorded amount.

        The brand quoted 100 and the row says 100; letting a larger transfer
        silently raise the claim would make the recorded amount mean something
        other than what was agreed.
        """
        dep = record_funding(
            self.brand, amount="100", chain_id=CHAIN, tx_hash=TX_B, token_symbol=TOKEN
        )
        with chain_showing(amount_units=500 * ONE):
            confirm_funding(dep)
        self.assertEqual(confirmed_funded_balance(self.brand), Decimal("100"))


class PendingFundingTaskTests(TestCase):
    """The retry path, so a brand is not left waiting on a scheduler they cannot see.

    A transfer is often mined before it is deep enough to credit, and an RPC
    outage can strand a deposit that was genuinely paid for. Both are fixed by
    asking the chain again, so the task must credit once the chain agrees — and
    must not credit while it does not.
    """

    def setUp(self):
        allowlist_usdg()
        _, self.brand = make_brand()
        self.dep = record_funding(
            self.brand, amount="100", chain_id=CHAIN, tx_hash=TX_A, token_symbol=TOKEN
        )

    def test_a_deposit_is_confirmed_once_the_chain_catches_up(self):
        # First pass: the transfer is not buried yet.
        with chain_showing(block_number=100, head=100):
            result = confirm_pending_fundings()
        self.assertEqual(result, {"confirmed": 0, "still_pending": 1})
        self.assertEqual(confirmed_funded_balance(self.brand), Decimal("0"))

        # Second pass, after the chain has moved on.
        with chain_showing(block_number=90, head=100):
            result = confirm_pending_fundings()
        self.assertEqual(result, {"confirmed": 1, "still_pending": 0})
        self.assertEqual(confirmed_funded_balance(self.brand), Decimal("100"))

    def test_an_rpc_outage_leaves_the_deposit_pending_rather_than_failing_loudly(self):
        with chain_showing(node=False):
            result = confirm_pending_fundings()
        self.assertEqual(result, {"confirmed": 0, "still_pending": 1})
        self.dep.refresh_from_db()
        self.assertEqual(self.dep.status, FundingStatus.PENDING)

    def test_the_task_is_scheduled(self):
        entry = settings.CELERY_BEAT_SCHEDULE["confirm-pending-fundings"]
        self.assertEqual(entry["task"], "apps.blockchain.tasks.confirm_pending_fundings")


class FundingServiceTests(TestCase):
    def setUp(self):
        # Every test in this class that credits money needs USDG allowlisted:
        # verification reads the token's real address and decimals from here,
        # so a token the platform has never heard of is not creditable.
        self.token = allowlist_usdg()

    def test_deposit_starts_pending_and_does_not_count_as_funded(self):
        _, brand = make_brand()
        dep = record_funding(brand, amount="100", chain_id=CHAIN, tx_hash=TX_A)
        # Recording is not crediting: an unverified transfer is not money yet.
        self.assertEqual(dep.status, FundingStatus.PENDING)
        self.assertEqual(confirmed_funded_balance(brand), Decimal("0"))

        with chain_showing(amount_units=100 * ONE):
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
        dep = record_funding(brand, amount="575", chain_id=CHAIN, tx_hash=TX_A)
        with chain_showing(amount_units=575 * ONE):
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
        dep = record_funding(brand, amount="100", chain_id=CHAIN, tx_hash=TX_A)
        with chain_showing(amount_units=100 * ONE):
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

    def test_confirming_an_unverified_deposit_is_refused_over_http(self):
        """The API path, restated. A brand posting its own deposit id credits nothing.

        This test used to be named `test_confirming_a_deposit_credits_the_balance`
        and asserted the opposite: that any authenticated brand could confirm
        its own unverified deposit and receive a balance. The endpoint itself
        was correct in what it exposed — a confirmation trigger — and wrong in
        trusting the caller for the outcome.
        """
        allowlist_usdg()
        user, _ = make_brand()
        client = authed(user)
        created = client.post(
            "/api/v1/brand/funding/",
            {"amount": "100", "chain_id": CHAIN, "tx_hash": TX_A},
            format="json",
        )
        with chain_showing(node=False):
            response = client.post(
                f"/api/v1/brand/funding/{created.data['id']}/confirm/", {}, format="json"
            )
        self.assertEqual(response.status_code, 400)
        balance = client.get("/api/v1/brand/funding/").data["confirmed_balance"]
        self.assertEqual(Decimal(balance), Decimal("0"))
        self.assertEqual(
            BrandFunding.objects.get(pk=created.data["id"]).status, FundingStatus.PENDING
        )

    def test_a_brand_can_confirm_its_own_deposit_once_the_chain_shows_it(self):
        """Triggering verification is allowed; the chain still decides the outcome.

        The brand needs a way to ask "has my money landed yet?" without an
        operator in the loop, so the endpoint stays available to them. What
        changed is that the answer comes from a receipt.
        """
        allowlist_usdg()
        user, _ = make_brand()
        client = authed(user)
        created = client.post(
            "/api/v1/brand/funding/",
            {"amount": "100", "chain_id": CHAIN, "tx_hash": TX_A},
            format="json",
        )
        with chain_showing(amount_units=100 * ONE):
            response = client.post(
                f"/api/v1/brand/funding/{created.data['id']}/confirm/", {}, format="json"
            )
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

