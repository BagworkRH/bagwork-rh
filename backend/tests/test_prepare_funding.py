"""Stage 6 funding rehearsal tooling: `manage.py prepare_funding`."""
from decimal import Decimal
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.blockchain.deposits import VerifiedTransfer
from apps.campaigns.models import BrandFunding, Campaign, CampaignStatus, FundingStatus

from .helpers import make_token_config

USDG = "0x00000000000000000000000000000000000000EE"
TREASURY = "0x00000000000000000000000000000000000000FF"
TX = "0x" + "ab" * 32


def _verified(amount=Decimal("5")):
    return VerifiedTransfer(
        tx_hash=TX,
        chain_id=46630,
        block_number=131000000,
        confirmations=5,
        token_symbol="USDG",
        token_address=USDG,
        from_address="0x1111111111111111111111111111111111111111",
        to_address=TREASURY,
        amount=amount,
    )


def _patch_verify(amount=Decimal("5")):
    return mock.patch("apps.campaigns.funding.verify_deposit", return_value=_verified(amount))


@override_settings(
    DEBUG=True,
    CHAIN_ID=46630,
    FUNDING_TOKEN_SYMBOL="USDG",
    FUNDING_TREASURY_ADDRESS=TREASURY,
)
class PrepareFundingCommandTests(TestCase):
    def setUp(self):
        make_token_config(symbol="USDG", chain_id=46630, address=USDG, decimals=6)

    def test_records_then_confirms_a_deposit(self):
        with _patch_verify():
            call_command("prepare_funding", company="Acme", amount="5", tx_hash=TX)

        funding = BrandFunding.objects.get()
        self.assertEqual(funding.status, FundingStatus.CONFIRMED)
        self.assertEqual(funding.amount, Decimal("5"))
        self.assertEqual(funding.verified_block, 131000000)
        self.assertEqual(funding.verified_sender, "0x1111111111111111111111111111111111111111")

    def test_launches_a_funded_brand_campaign(self):
        with _patch_verify():
            call_command(
                "prepare_funding", company="Acme", amount="5", tx_hash=TX, slug="acme-launch", launch=True
            )

        campaign = Campaign.objects.get(slug="acme-launch")
        self.assertEqual(campaign.status, CampaignStatus.ACTIVE)
        self.assertIsNotNone(campaign.funding_brand)

    def test_launch_is_refused_when_the_campaign_outruns_the_balance(self):
        with _patch_verify():
            call_command("prepare_funding", company="Acme", amount="5", tx_hash=TX, slug="big")

        # Force the campaign's budget far above the brand's confirmed balance.
        Campaign.objects.filter(slug="big").update(budget=Decimal("1000"), remaining_budget=Decimal("1000"))

        tx2 = "0x" + "cd" * 32
        with _patch_verify():
            with self.assertRaises(CommandError):
                call_command(
                    "prepare_funding", company="Acme", amount="5", tx_hash=tx2, slug="big", launch=True
                )


class PrepareFundingGuardTests(TestCase):
    def test_refuses_when_debug_is_off(self):
        with self.assertRaises(CommandError):
            call_command("prepare_funding", company="Acme", amount="5", tx_hash=TX)
