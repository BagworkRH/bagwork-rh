"""Stage 6 rehearsal tooling: `manage.py prepare_claim` (dev/testnet only)."""
import json
import os
import tempfile

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.rewards.models import Reward, RewardStatus
from apps.wallets.models import Claim, ClaimStatus

from .helpers import make_token_config, signer_settings

WALLET = "0x1111111111111111111111111111111111111111"
CONTRACT = "0x00000000000000000000000000000000000000BB"
USDG = "0x00000000000000000000000000000000000000EE"


@override_settings(DEBUG=True)
@signer_settings(contract_address=CONTRACT)
class PrepareClaimCommandTests(TestCase):
    def _prepare(self, out):
        make_token_config(symbol="USDG", chain_id=46630, address=USDG, decimals=6)
        call_command(
            "prepare_claim",
            seller_address=WALLET,
            amount="1",
            symbol="USDG",
            chain_id=46630,
            out=out,
        )

    def test_writes_a_usdg_authorization_for_the_wallet(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "auth.json")
            self._prepare(out)
            with open(out, encoding="utf-8") as handle:
                data = json.load(handle)
        # 1 USDG at 6 decimals is 1_000_000 smallest units.
        self.assertEqual(data["token_symbol"], "USDG")
        self.assertEqual(data["amount_smallest_unit"], 1_000_000)
        self.assertEqual(data["wallet"], WALLET)
        self.assertEqual(data["transaction"]["to"], CONTRACT)
        self.assertTrue(data["signature"].startswith("0x"))

    def test_creates_an_available_reward_and_a_signing_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._prepare(os.path.join(tmp, "auth.json"))
        claim = Claim.objects.get()
        self.assertEqual(claim.status, ClaimStatus.SIGNING)
        self.assertEqual(claim.reward.status, RewardStatus.AVAILABLE)
        self.assertEqual(Reward.objects.count(), 1)


@signer_settings(contract_address=CONTRACT)
class PrepareClaimGuardTests(TestCase):
    def test_refuses_when_debug_is_off(self):
        # Django forces DEBUG=False under test, so the rehearsal tool must refuse.
        with self.assertRaises(CommandError):
            call_command(
                "prepare_claim",
                seller_address=WALLET,
                amount="1",
                symbol="USDG",
                chain_id=46630,
                out="unused.json",
            )
