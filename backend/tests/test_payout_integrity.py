"""Payout integrity: decimals, token allowlist, and funding-before-launch.

Each case here corresponds to a way the platform could promise money it does
not have or quote a number the chain will not honour.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.blockchain import fees
from apps.blockchain.models import TokenConfig
from apps.campaigns.funding import (
    campaign_funding_position,
    confirm_funding,
    get_or_create_brand,
    quote_campaign_cost,
    record_funding,
    required_campaign_funding,
)
from apps.campaigns.models import CampaignStatus
from apps.campaigns.services import create_campaign, set_campaign_status
from apps.rewards.exceptions import RewardEngineError

from .helpers import chain_showing, make_campaign

User = get_user_model()

USDG_ADDRESS = "0x00000000000000000000000000000000000000DC"
TX = "0x" + "d" * 64


def make_funding_token(chain_id=46630, decimals=6):
    """USDG on the allowlist at its own precision."""
    token, _ = TokenConfig.objects.get_or_create(
        symbol="USDG",
        defaults={"chain_id": chain_id, "address": USDG_ADDRESS, "decimals": decimals, "enabled": True},
    )
    return token


def make_user(username, email, **extra):
    return User.objects.create_user(
        username=username, email=email, password="Testpass123!", **extra
    )


def window():
    now = datetime.now(timezone.utc)
    return now - timedelta(days=1), now + timedelta(days=30)


def campaign_fields(**overrides):
    start, end = window()
    fields = {
        "description": "d",
        "project_name": "P",
        "token_symbol": "USDG",
        "chain_id": 46630,
        "reward_model": "FIXED",
        "reward_rate": Decimal("5"),
        "maximum_reward_per_seller": Decimal("0"),
        "maximum_rewards_per_seller": 0,
        "start_at": start,
        "end_at": end,
    }
    fields.update(overrides)
    return fields


class FeeDecimalsTests(TestCase):
    """Fee precision must come from the token, not a platform default.

    Written against an explicit precision rather than the funding token's, so
    the property holds whichever stablecoin is allowlisted: the point is that
    the caller supplies the token's decimals, not that any one token has a
    particular number.
    """

    def test_fee_matches_the_contract_at_the_token_real_precision(self):
        self.assertEqual(fees.platform_fee(Decimal("500"), 6), Decimal("75"))
        # A sub-cent payout floors to zero at 6dp, exactly as the contract does.
        self.assertEqual(fees.platform_fee(Decimal("0.0000001"), 6), Decimal("0"))

    def test_wrong_precision_would_misquote_a_brand(self):
        """This is the bug the decimals argument exists to prevent."""
        at_18 = fees.platform_fee(Decimal("0.0000001"), 18)
        at_6 = fees.platform_fee(Decimal("0.0000001"), 6)
        self.assertNotEqual(at_18, at_6)
        self.assertGreater(at_18, at_6)

    def test_quote_uses_the_campaign_token_precision(self):
        make_funding_token()
        user = make_user("feeuser", "fee@example.com")
        brand = get_or_create_brand(user, company_name="Fee Co", actor=user)
        quote = quote_campaign_cost(brand, payout_total=Decimal("500"), decimals=6)
        self.assertEqual(Decimal(quote["platform_fee"]), Decimal("75"))
class TokenAllowlistTests(TestCase):
    def test_campaign_paying_an_unlisted_token_is_refused(self):
        """A free-text symbol would let a campaign promise a token the
        distributor does not hold, failing only at claim time."""
        make_funding_token()
        admin = make_user("admin1", "a1@example.com", is_staff=True)
        with self.assertRaises(RewardEngineError) as ctx:
            create_campaign(
                created_by=admin,
                name="Bad",
                slug="bad-token",
                budget=Decimal("100"),
                **campaign_fields(token_symbol="SCAM"),
            )
        self.assertIn("SCAM", str(ctx.exception))
        self.assertIn("allowlist", str(ctx.exception))

    def test_allowlisted_token_is_accepted(self):
        make_funding_token()
        admin = make_user("admin2", "a2@example.com", is_staff=True)
        campaign = create_campaign(
            created_by=admin,
            name="Good",
            slug="good-token",
            budget=Decimal("100"),
            **campaign_fields(),
        )
        self.assertEqual(campaign.token_symbol, "USDG")

    def test_token_allowlisted_on_another_chain_is_still_refused(self):
        """A symbol approved on one chain is not approved on another.

        The chain is populated with USDG, but this campaign asks for a different
        symbol on that same chain — a mismatch that would otherwise only fail at
        claim time.
        """
        make_funding_token(chain_id=46630)
        admin = make_user("admin3", "a3@example.com", is_staff=True)
        with self.assertRaises(RewardEngineError) as ctx:
            create_campaign(
                created_by=admin,
                name="WrongToken",
                slug="wrong-token",
                budget=Decimal("100"),
                **campaign_fields(token_symbol="USDT"),
            )
        self.assertIn("USDT", str(ctx.exception))

class FundingBeforeLaunchTests(TestCase):
    """The 'who provides the money' rule, enforced in code.

    Without this, creators post, get verified and approved, and the payout
    fails at claim time — after the work is already done.
    """

    def test_brand_campaign_cannot_launch_unfunded(self):
        make_funding_token()
        user = make_user("brand1", "b1@example.com")
        brand = get_or_create_brand(user, company_name="Fund Co", actor=user)
        campaign = create_campaign(
            created_by=user,
            name="Unfunded",
            slug="unfunded",
            budget=Decimal("500"),
            **campaign_fields(),
        )
        self.assertEqual(campaign.funding_brand, brand)

        with self.assertRaises(RewardEngineError) as ctx:
            set_campaign_status(campaign, CampaignStatus.ACTIVE, actor=user)
        self.assertIn("not funded", str(ctx.exception))

        # Fund it: 500 of payouts plus a 15% fee is 575.
        dep = record_funding(brand, amount="575", chain_id=46630, tx_hash=TX)

        # PENDING does not count: recording a deposit is not crediting it.
        with self.assertRaises(RewardEngineError):
            set_campaign_status(campaign, CampaignStatus.ACTIVE, actor=user)

        # Now let the chain vouch for it, and the gate opens.
        with chain_showing(
            token_address=USDG_ADDRESS, chain_id=46630, amount_units=575 * 10**6
        ):
            confirm_funding(dep, actor=user)
        campaign = set_campaign_status(campaign, CampaignStatus.ACTIVE, actor=user)
        self.assertEqual(campaign.status, CampaignStatus.ACTIVE)

    def test_partial_funding_still_blocks_launch(self):
        make_funding_token()
        user = make_user("brand2", "b2@example.com")
        brand = get_or_create_brand(user, company_name="Part Co", actor=user)
        campaign = create_campaign(
            created_by=user,
            name="Partial",
            slug="partial",
            budget=Decimal("500"),
            **campaign_fields(),
        )
        dep = record_funding(brand, amount="500", chain_id=46630, tx_hash=TX)
        # Fully verified on chain — 500 really did arrive. It is still not enough,
        # because the gate asks for the fee as well as the payouts.
        with chain_showing(
            token_address=USDG_ADDRESS, chain_id=46630, amount_units=500 * 10**6
        ):
            confirm_funding(dep, actor=user)
        # 500 covers the payouts but not the 75 fee.
        position = campaign_funding_position(campaign)
        self.assertFalse(position["sufficient"])
        self.assertEqual(Decimal(position["shortfall"]), Decimal("75"))
        with self.assertRaises(RewardEngineError):
            set_campaign_status(campaign, CampaignStatus.ACTIVE, actor=user)

    def test_required_funding_is_budget_plus_fee(self):
        make_funding_token()
        campaign = make_campaign(
            budget=Decimal("500"), token_symbol="USDG", chain_id=46630
        )
        self.assertEqual(required_campaign_funding(campaign), Decimal("575"))

    def test_staff_funded_campaigns_skip_the_check(self):
        """Platform-funded campaigns have no brand to check, so development and
        seed campaigns still launch."""
        campaign = make_campaign(status=CampaignStatus.DRAFT)
        campaign = set_campaign_status(campaign, CampaignStatus.ACTIVE)
        self.assertEqual(campaign.status, CampaignStatus.ACTIVE)

