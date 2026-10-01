"""Chain listener, ledger and reconciliation tests (Spec 04).

These exercise the pieces that run against a chain: event decoding and claim
confirmation, ledger accounting, and reconciliation. Live-RPC paths stay in
their "disabled" branch because no node is reachable from the test suite.
"""
from decimal import Decimal

from django.db.models import Sum
from django.test import TestCase
from eth_abi import encode as abi_encode
from eth_utils import to_canonical_address, to_checksum_address
from hexbytes import HexBytes

from apps.blockchain import listener
from apps.blockchain.models import LedgerAction, LedgerEntry
from apps.blockchain.reconciliation import internal_claimed_total, reconcile
from apps.rewards.services import approve_reward, calculate_reward, make_available
from apps.wallets.models import Claim, ClaimStatus
from apps.wallets.services import create_claim, mark_claim_confirmed

from .helpers import (
    chain_settings,
    make_campaign,
    make_token_config,
    make_user,
    make_verified_post,
    make_verified_wallet,
)

WALLET = "0x1111111111111111111111111111111111111111"
TOKEN = "0x00000000000000000000000000000000000000AA"


def make_log(reward_id, wallet, token, amount, nonce):
    """Build the topics/data for a synthetic RewardClaimed event."""
    topics = [
        listener.CLAIM_TOPIC0,
        HexBytes(reward_id.to_bytes(32, "big")),
        HexBytes(bytes(12) + to_canonical_address(wallet)),
        HexBytes(bytes(12) + to_canonical_address(token)),
    ]
    data = abi_encode(["uint256", "uint256"], [amount, nonce])
    return topics, data


def setup_claim(nonce="0" * 62 + "01", external_id="listener-1", with_token=True):
    if with_token:
        make_token_config(symbol="TST", address=TOKEN)
    user, profile = make_user()
    campaign = make_campaign(budget=Decimal("100"), reward_rate=Decimal("5"))
    post = make_verified_post(profile, campaign, external_id=external_id)
    reward = calculate_reward(campaign, post, profile, user=user)
    approve_reward(reward, actor=user)
    make_available(reward, actor=user)
    reward.refresh_from_db()
    wallet = make_verified_wallet(profile, address=WALLET)
    claim = create_claim(profile, wallet, reward, actor=user)
    Claim.objects.filter(pk=claim.pk).update(nonce=nonce)
    claim.refresh_from_db()
    return user, profile, reward, claim


class EventDecodingTests(TestCase):
    def test_decode_reward_claimed_log(self):
        topics, data = make_log(7, WALLET, TOKEN, 5_000_000_000_000_000_000, 1)
        event = listener.decode_reward_claimed_log(topics, data)
        self.assertEqual(event["reward_id"], 7)
        self.assertEqual(
            to_checksum_address(event["wallet"]), to_checksum_address(WALLET)
        )
        self.assertEqual(to_checksum_address(event["token"]), to_checksum_address(TOKEN))
        self.assertEqual(event["amount"], 5_000_000_000_000_000_000)
        self.assertEqual(event["nonce"], 1)

    def test_decode_ignores_unrelated_logs(self):
        topics, data = make_log(7, WALLET, TOKEN, 1, 1)
        topics[0] = HexBytes(b"\x00" * 32)
        self.assertIsNone(listener.decode_reward_claimed_log(topics, data))
class HandleRewardClaimedTests(TestCase):
    def test_matching_event_confirms_claim_and_reward(self):
        _, _, reward, claim = setup_claim()
        topics, data = make_log(reward.pk, WALLET, TOKEN, claim.amount_smallest_unit, 1)
        event = listener.decode_reward_claimed_log(topics, data)

        result = listener.handle_reward_claimed(event, transaction_hash="0x" + "ab" * 32)
        self.assertEqual(result["status"], "confirmed")

        claim.refresh_from_db()
        reward.refresh_from_db()
        self.assertEqual(claim.status, ClaimStatus.CONFIRMED)
        self.assertEqual(claim.transaction_hash, "0x" + "ab" * 32)
        self.assertEqual(reward.status, "CLAIMED")

        entry = LedgerEntry.objects.filter(
            action=LedgerAction.CLAIM_CONFIRMED, claim=claim
        ).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.amount_smallest_unit, claim.amount_smallest_unit)
        self.assertEqual(entry.transaction_hash, "0x" + "ab" * 32)

    def test_nonce_with_leading_zeros_still_matches(self):
        # The stored nonce is a 64-char hex string with leading zero nibbles;
        # matching must compare integer values, not raw strings.
        _, _, reward, claim = setup_claim(nonce="0" * 60 + "0abc")
        topics, data = make_log(reward.pk, WALLET, TOKEN, claim.amount_smallest_unit, 0xABC)
        event = listener.decode_reward_claimed_log(topics, data)
        self.assertEqual(listener.handle_reward_claimed(event)["status"], "confirmed")

    def test_confirmation_is_idempotent(self):
        _, _, reward, claim = setup_claim()
        topics, data = make_log(reward.pk, WALLET, TOKEN, claim.amount_smallest_unit, 1)
        event = listener.decode_reward_claimed_log(topics, data)
        listener.handle_reward_claimed(event, transaction_hash="0x" + "ab" * 32)
        second = listener.handle_reward_claimed(event, transaction_hash="0x" + "ab" * 32)
        self.assertEqual(second["status"], "already-confirmed")

    def test_unknown_nonce_is_reported(self):
        _, _, reward, claim = setup_claim()
        topics, data = make_log(reward.pk, WALLET, TOKEN, claim.amount_smallest_unit, 999)
        event = listener.decode_reward_claimed_log(topics, data)
        self.assertEqual(listener.handle_reward_claimed(event)["status"], "no-matching-claim")

    def test_unknown_reward_is_reported(self):
        setup_claim()
        topics, data = make_log(4242, WALLET, TOKEN, 1, 1)
        event = listener.decode_reward_claimed_log(topics, data)
        self.assertEqual(listener.handle_reward_claimed(event)["status"], "no-matching-claim")


class ListenerDisabledTests(TestCase):
    def test_poll_reports_disabled_without_rpc(self):
        result = listener.poll_reward_claimed_events()
        self.assertEqual(result["status"], "disabled")

    @chain_settings()
    def test_poll_reports_disabled_when_node_unreachable(self):
        # RPC_URL is configured but nothing is listening; get_web3() returns None.
        result = listener.poll_reward_claimed_events()
        self.assertEqual(result["status"], "disabled")


class ReconciliationTests(TestCase):
    def test_reconcile_disabled_without_chain_config(self):
        results = reconcile()
        self.assertEqual(results[0]["status"], "disabled")

    def test_internal_claimed_total_sums_confirmed_claims_only(self):
        token = make_token_config(symbol="TST", address=TOKEN)
        _, _, _, claim = setup_claim(with_token=False)

        self.assertEqual(internal_claimed_total(token), Decimal("0"))
        mark_claim_confirmed(claim, "0x" + "ef" * 32)
        self.assertEqual(internal_claimed_total(token), Decimal("5.000000000000000000"))



class PlatformFeeLedgerTests(TestCase):
    """The 15% fee is booked as a separate treasury credit, never deducted
    from the creator's payout line (Spec 04)."""

    def test_fee_is_a_separate_ledger_entry_and_creator_keeps_full_payout(self):
        make_token_config(symbol="TST", address=TOKEN)
        _, _, _, claim = setup_claim(with_token=False)
        mark_claim_confirmed(claim, "0x" + "ab" * 32)

        creator_line = LedgerEntry.objects.get(
            action=LedgerAction.CLAIM_CONFIRMED, claim=claim
        )
        fee_line = LedgerEntry.objects.get(
            action=LedgerAction.FEE_ACCRUED, claim=claim
        )

        # The creator is credited the FULL signed amount, never a reduced one.
        self.assertEqual(creator_line.amount, Decimal("5.000000000000000000"))
        # The fee is 15% of the payout, in its own entry.
        self.assertEqual(fee_line.amount, Decimal("0.750000000000000000"))
        # Both reference the same on-chain transaction for reconciliation.
        self.assertEqual(creator_line.transaction_hash, fee_line.transaction_hash)

    def test_fee_never_shrinks_creator_credited_total(self):
        token = make_token_config(symbol="TST", address=TOKEN)
        _, _, _, claim = setup_claim(with_token=False)
        mark_claim_confirmed(claim, "0x" + "cd" * 32)

        # The reconciliation figure is creator payouts only, so introducing the
        # fee must not change what the platform owes creators.
        self.assertEqual(
            internal_claimed_total(token), Decimal("5.000000000000000000")
        )
        fee_total = LedgerEntry.objects.filter(
            action=LedgerAction.FEE_ACCRUED
        ).aggregate(total=Sum("amount"))["total"]
        self.assertEqual(fee_total, Decimal("0.750000000000000000"))
