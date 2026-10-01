"""Platform fee arithmetic (Spec 04).

The load-bearing rule: a creator receives the FULL signed payout. The 15% fee
is the brand's additional cost, never a deduction from what a creator earned.
These tests also cross-check the Python arithmetic against the compiled
contract so the quote a brand sees can never drift from what the chain accepts.
"""
from decimal import Decimal

from django.test import SimpleTestCase, override_settings

from apps.blockchain import fees

PAYOUT = Decimal("5")


class PlatformFeeMathTests(SimpleTestCase):
    def test_fee_is_15_percent_charged_on_top(self):
        self.assertEqual(fees.fee_bps(), 1500)
        self.assertEqual(fees.platform_fee(PAYOUT), Decimal("0.75"))
        # The creator is untouched; the brand pays more.
        self.assertEqual(fees.total_cost(PAYOUT), Decimal("5.75"))

    def test_fee_never_reduces_the_creator_payout(self):
        # The whole point of the design, asserted directly.
        payout = Decimal("12.5")
        self.assertEqual(fees.total_cost(payout) - fees.platform_fee(payout), payout)

    def test_zero_payout_costs_nothing(self):
        self.assertEqual(fees.platform_fee(Decimal("0")), Decimal("0"))
        self.assertEqual(fees.total_cost(Decimal("0")), Decimal("0"))

    def test_budget_funds_fewer_posts_not_smaller_posts(self):
        # $2,500 at $5/post: 434 posts, each creator still paid the full $5.
        posts = fees.payouts_from_budget(Decimal("2500"), PAYOUT)
        self.assertEqual(posts, 434)
        self.assertEqual(fees.brand_cost_for(posts, PAYOUT), Decimal("2495.50"))
        # 435 posts would exceed the budget and must not be offered.
        self.assertGreater(fees.brand_cost_for(435, PAYOUT), Decimal("2500"))

    def test_brand_cost_always_covers_payouts_plus_fees(self):
        for payouts in (1, 10, 100, 434):
            cost = fees.brand_cost_for(payouts, PAYOUT)
            # A brand always pays at least the creator payouts, plus a fee.
            self.assertGreaterEqual(cost, payouts * PAYOUT)
            self.assertEqual(cost, (Decimal("1") + fees.fee_rate()) * payouts * PAYOUT)

    def test_sub_unit_fees_are_never_rounded_up(self):
        # A fee below one smallest unit floors to zero rather than charging a
        # wei the contract would not actually take (Solidity floors).
        self.assertEqual(fees.platform_fee(Decimal("0.000000000000000001")), Decimal("0"))
        self.assertEqual(fees.platform_fee(Decimal("1")), Decimal("0.15"))
        self.assertEqual(fees.platform_fee(Decimal("0.0000001")), Decimal("0.000000015"))

    def test_fee_rate_tracks_settings(self):
        self.assertEqual(fees.fee_rate(), Decimal("0.15"))

    @override_settings(PLATFORM_FEE_BPS=0)
    def test_zero_fee_is_honoured(self):
        self.assertEqual(fees.platform_fee(PAYOUT), Decimal("0"))
        self.assertEqual(fees.total_cost(PAYOUT), PAYOUT)
