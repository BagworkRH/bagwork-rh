"""Emergency controls and scheduled-task tests (Spec 04).

Covers pausing claims, disabling tokens, signer rotation, the staff-only
blockchain status/control endpoints, and the claim-expiry task.
"""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.blockchain import services as chain
from apps.blockchain.models import PlatformControl
from apps.blockchain.tasks import (
    expire_stale_claims,
    monitor_anomalous_claims,
    process_claim_events,
    reconcile_blockchain_ledger,
)
from apps.campaigns.models import Campaign, CampaignStatus
from apps.rewards.exceptions import RewardEngineError
from apps.rewards.services import approve_reward, calculate_reward, make_available
from apps.wallets.models import Claim, ClaimStatus
from apps.wallets.services import create_claim

from .helpers import (
    make_campaign,
    make_staff,
    make_token_config,
    make_user,
    make_verified_post,
    make_verified_wallet,
    signer_settings,
)

WALLET = "0x1111111111111111111111111111111111111111"
CONTRACT = "0x00000000000000000000000000000000000000BB"
TOKEN = "0x00000000000000000000000000000000000000AA"


def setup_claim(external_id="ops-1"):
    user, profile, reward = setup_available_reward(external_id)
    wallet = make_verified_wallet(profile, address=WALLET)
    claim = create_claim(profile, wallet, reward, actor=user)
    return user, profile, reward, claim


def setup_available_reward(external_id="ops-1"):
    """An AVAILABLE reward with no claim yet."""
    make_token_config(symbol="TST", address=TOKEN)
    user, profile = make_user()
    campaign = make_campaign(budget=Decimal("100"), reward_rate=Decimal("5"))
    post = make_verified_post(profile, campaign, external_id=external_id)
    reward = calculate_reward(campaign, post, profile, user=user)
    approve_reward(reward, actor=user)
    make_available(reward, actor=user)
    reward.refresh_from_db()
    return user, profile, reward


class ClaimingPauseTests(TestCase):
    def test_pausing_claiming_blocks_new_claims(self):
        user, profile, reward = setup_available_reward()
        wallet = make_verified_wallet(profile, address=WALLET)
        chain.set_claiming_paused(True, actor=user)
        self.assertTrue(chain.is_claiming_paused())
        with self.assertRaises(RewardEngineError):
            create_claim(profile, wallet, reward, actor=user)

    def test_resuming_claiming_allows_claims(self):
        user, profile, reward = setup_available_reward(external_id="ops-2")
        wallet = make_verified_wallet(profile, address=WALLET)
        chain.set_claiming_paused(True, actor=user)
        chain.set_claiming_paused(False, actor=user)
        self.assertFalse(chain.is_claiming_paused())

        claim = create_claim(profile, wallet, reward, actor=user)
        self.assertEqual(claim.status, ClaimStatus.CREATED)

    def test_pause_state_is_a_single_row(self):
        chain.set_claiming_paused(True)
        chain.set_claiming_paused(False)
        self.assertEqual(PlatformControl.objects.filter(key="claiming").count(), 1)


class CampaignDisableTests(TestCase):
    def test_claims_blocked_when_campaign_disabled(self):
        user, profile, reward = setup_available_reward(external_id="cd-1")
        wallet = make_verified_wallet(profile, address=WALLET)
        Campaign.objects.filter(pk=reward.campaign_id).update(status=CampaignStatus.PAUSED)

        with self.assertRaises(RewardEngineError):
            create_claim(profile, wallet, reward, actor=user)


class DisabledTokenTests(TestCase):
    @signer_settings(contract_address=CONTRACT)
    def test_disabled_token_blocks_authorization(self):
        token = make_token_config(symbol="TST", address=TOKEN)
        _, _, _, claim = setup_claim(external_id="ops-3")
        chain.set_token_enabled(token, False)
        with self.assertRaises(chain.BlockchainError):
            chain.get_claim_authorization_payload(claim)


class SignerRotationTests(TestCase):
    @signer_settings(contract_address=CONTRACT)
    def test_rotated_signer_invalidates_previous_authorization(self):
        _, _, _, claim = setup_claim(external_id="ops-4")
        payload = chain.get_claim_authorization_payload(claim)
        self.assertTrue(chain.verify_authorization(claim, payload["signature"]))

        chain.rotate_claim_signer("0x" + "33" * 32)
        self.assertFalse(chain.verify_authorization(claim, payload["signature"]))
class BlockchainApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_status_requires_staff(self):
        user, _ = make_user()
        self.client.force_authenticate(user=user)
        self.assertEqual(self.client.get("/api/v1/blockchain/status/").status_code, 403)

    @signer_settings(contract_address=CONTRACT)
    def test_status_reports_configuration_for_staff(self):
        self.client.force_authenticate(user=make_staff())
        resp = self.client.get("/api/v1/blockchain/status/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["signer_configured"])
        self.assertFalse(resp.data["claiming_paused"])
        self.assertEqual(resp.data["contract_address"], CONTRACT)

    def test_control_requires_staff(self):
        user, _ = make_user()
        self.client.force_authenticate(user=user)
        resp = self.client.post(
            "/api/v1/blockchain/control/", {"action": "pause_claiming"}, format="json"
        )
        self.assertEqual(resp.status_code, 403)

    def test_control_pauses_and_resumes(self):
        self.client.force_authenticate(user=make_staff())
        paused = self.client.post(
            "/api/v1/blockchain/control/", {"action": "pause_claiming"}, format="json"
        )
        self.assertEqual(paused.status_code, 200)
        self.assertTrue(paused.data["claiming_paused"])
        self.assertTrue(chain.is_claiming_paused())

        resumed = self.client.post(
            "/api/v1/blockchain/control/", {"action": "resume_claiming"}, format="json"
        )
        self.assertFalse(resumed.data["claiming_paused"])

    def test_control_rejects_unknown_action(self):
        self.client.force_authenticate(user=make_staff())
        resp = self.client.post(
            "/api/v1/blockchain/control/", {"action": "launch_missiles"}, format="json"
        )
        self.assertEqual(resp.status_code, 400)


class ScheduledTaskTests(TestCase):
    def test_process_claim_events_reports_disabled(self):
        result = process_claim_events()
        self.assertEqual(result["status"], "disabled")

    def test_reconcile_task_reports_disabled(self):
        self.assertEqual(reconcile_blockchain_ledger()[0]["status"], "disabled")

    def test_monitor_task_returns_stats(self):
        self.assertEqual(monitor_anomalous_claims(threshold=5), {"checked": 0, "flagged": []})

    def test_expire_stale_claims_releases_reward(self):
        _, _, reward, claim = setup_claim(external_id="ops-5")
        Claim.objects.filter(pk=claim.pk).update(
            status=ClaimStatus.CREATED,
            expired_at=timezone.now() - timedelta(hours=2),
        )

        result = expire_stale_claims()
        self.assertEqual(result["expired"], 1)

        claim.refresh_from_db()
        reward.refresh_from_db()
        self.assertEqual(claim.status, ClaimStatus.EXPIRED)
        self.assertEqual(reward.status, "AVAILABLE")

    def test_expire_task_ignores_fresh_claims(self):
        _, _, _, claim = setup_claim(external_id="ops-6")
        Claim.objects.filter(pk=claim.pk).update(
            status=ClaimStatus.CREATED,
            expired_at=timezone.now() + timedelta(hours=1),
        )
        self.assertEqual(expire_stale_claims()["expired"], 0)
