"""Staff back-office API tests (Spec 05 Phase 7 · Spec 01 Admin UI).

Covers permission boundaries (staff only), the directories, the review actions,
and that every privileged action leaves an audit entry.
"""
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit import risk
from apps.audit.models import AuditLog, RiskFlag, RiskStatus
from apps.campaigns.models import CampaignStatus
from apps.campaigns.services import set_campaign_status
from apps.rewards.exceptions import RewardEngineError
from apps.rewards.models import RewardStatus
from apps.rewards.services import approve_reward, calculate_reward, make_available
from apps.sellers.models import SellerProfile
from apps.social.models import PostVerificationStatus, SocialPost
from apps.wallets.models import ClaimStatus
from apps.wallets.services import create_claim

from .helpers import (
    make_campaign,
    make_staff,
    make_token_config,
    make_user,
    make_verified_wallet,
)

WALLET = "0x1111111111111111111111111111111111111111"

# Every staff-only route, so the boundary is asserted in one place.
ADMIN_ROUTES = (
    ("get", "/api/v1/admin/overview/"),
    ("get", "/api/v1/admin/sellers/"),
    ("get", "/api/v1/admin/campaigns/"),
    ("get", "/api/v1/admin/posts/"),
    ("get", "/api/v1/admin/rewards/"),
    ("get", "/api/v1/admin/claims/"),
    ("get", "/api/v1/admin/risk/"),
    ("get", "/api/v1/admin/audit-logs/"),
    ("get", "/api/v1/admin/settings/"),
)


def make_reward(  # noqa: PLR0913 - test helper with sensible defaults
    external_id="admin-1",
    budget=Decimal("100"),
    rate=Decimal("5"),
    *,
    email=None,
    username=None,
    slug=None,
):
    """An AVAILABLE reward with a wallet ready to claim it."""
    user_kwargs = {}
    if email:
        user_kwargs["email"] = email
    if username:
        user_kwargs["username"] = username
    user, profile = make_user(**user_kwargs)
    campaign_kwargs = {"budget": budget, "reward_rate": rate}
    if slug:
        campaign_kwargs["slug"] = slug
    campaign = make_campaign(**campaign_kwargs)
    post = SocialPost.objects.create(
        account=None,
        external_post_id=external_id,
        seller=profile,
        campaign=campaign,
        post_url=f"https://x.com/status/{external_id}",
        text_snapshot="promo",
        published_at=timezone.now(),
        verification_status=PostVerificationStatus.VERIFIED,
    )
    reward = calculate_reward(campaign, post, profile, user=user)
    return user, profile, campaign, post, reward


class AdminPermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_anonymous_is_rejected(self):
        for method, url in ADMIN_ROUTES:
            response = getattr(self.client, method)(url)
            self.assertIn(response.status_code, (401, 403), f"{url} -> {response.status_code}")

    def test_regular_seller_is_rejected(self):
        user, _ = make_user()
        self.client.force_authenticate(user=user)
        for method, url in ADMIN_ROUTES:
            response = getattr(self.client, method)(url)
            self.assertEqual(response.status_code, 403, f"{url} -> {response.status_code}")

    def test_staff_can_read_every_directory(self):
        self.client.force_authenticate(user=make_staff())
        for method, url in ADMIN_ROUTES:
            response = getattr(self.client, method)(url)
            self.assertEqual(response.status_code, 200, f"{url} -> {response.status_code}")


class OverviewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=make_staff())

    def test_overview_reports_platform_statistics(self):
        _, _, _, _, reward = make_reward("overview-1")
        response = self.client.get("/api/v1/admin/overview/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["sellers"]["total"], 1)
        self.assertEqual(response.data["posts"]["total"], 1)
        self.assertEqual(response.data["rewards"]["pending_review"], 1)
        self.assertIn("risk", response.data)
        self.assertIn("audit_events_last_24h", response.data)
        self.assertEqual(response.data["campaigns"]["total"], 1)
        self.assertEqual(reward.status, RewardStatus.PENDING)


class SellerDirectoryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=make_staff())

    def test_seller_list_reports_owned_resources(self):
        _, profile, _, _, _ = make_reward("seller-1")
        make_verified_wallet(profile, address=WALLET)

        response = self.client.get("/api/v1/admin/sellers/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        row = response.data["results"][0]
        self.assertEqual(row["seller_code"], profile.seller_code)
        self.assertEqual(row["verified_wallets"], 1)
        self.assertEqual(row["posts"], 1)

    def test_search_filters_by_seller_code(self):
        _, profile, _, _, _ = make_reward("seller-2")
        make_reward("seller-3", email="second@example.com", username="second-seller", slug="second-campaign")

        response = self.client.get(
            "/api/v1/admin/sellers/", {"search": profile.seller_code}
        )
        self.assertEqual(response.data["count"], 1)

    def test_suspending_a_seller_is_audited_and_blocks_claims(self):
        user, profile, _, _, reward = make_reward("seller-4")
        make_token_config(symbol="TST")
        approve_reward(reward, actor=user)
        make_available(reward, actor=user)
        reward.refresh_from_db()
        wallet = make_verified_wallet(profile, address=WALLET)

        response = self.client.post(
            f"/api/v1/admin/sellers/{profile.pk}/status/",
            {"status": "SUSPENDED", "reason": "Chargeback investigation."},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], SellerProfile.Status.SUSPENDED)
        self.assertTrue(
            AuditLog.objects.filter(action="SELLER_STATUS_CHANGED", object_id=str(profile.pk)).exists()
        )

        profile.refresh_from_db()
        with self.assertRaises(RewardEngineError):
            create_claim(profile, wallet, reward, actor=user)

    def test_invalid_status_is_rejected(self):
        _, profile, _, _, _ = make_reward("seller-5")
        response = self.client.post(
            f"/api/v1/admin/sellers/{profile.pk}/status/",
            {"status": "BANNED"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)


class CampaignDirectoryTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=make_staff())

    def test_pausing_a_campaign_is_audited(self):
        _, _, campaign, _, _ = make_reward("campaign-1")
        response = self.client.post(
            f"/api/v1/admin/campaigns/{campaign.pk}/status/",
            {"status": "PAUSED", "reason": "Budget review."},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], CampaignStatus.PAUSED)
        self.assertTrue(
            AuditLog.objects.filter(action="CAMPAIGN_STATUS_CHANGED").exists()
        )

    def test_invalid_campaign_status_is_rejected(self):
        _, _, campaign, _, _ = make_reward("campaign-2")
        response = self.client.post(
            f"/api/v1/admin/campaigns/{campaign.pk}/status/",
            {"status": "ARCHIVED"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_campaign_filter_by_status(self):
        _, _, campaign, _, _ = make_reward("campaign-3")
        set_campaign_status(campaign, "PAUSED")

        paused = self.client.get("/api/v1/admin/campaigns/", {"status": "paused"})
        active = self.client.get("/api/v1/admin/campaigns/", {"status": "ACTIVE"})
        self.assertEqual(paused.data["count"], 1)
        self.assertEqual(active.data["count"], 0)


class PostReviewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=make_staff())

    def test_reject_requires_a_reason(self):
        _, _, _, post, _ = make_reward("post-1")
        response = self.client.post(
            f"/api/v1/admin/posts/{post.pk}/review/", {"decision": "reject"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_reject_applies_failure_state_with_reason(self):
        _, _, _, post, _ = make_reward("post-2")
        response = self.client.post(
            f"/api/v1/admin/posts/{post.pk}/review/",
            {
                "decision": "reject",
                "reason": "Duplicate campaign entry.",
                "rejection_status": "DUPLICATE",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["verification_status"], PostVerificationStatus.DUPLICATE)
        self.assertEqual(response.data["rejection_reason"], "Duplicate campaign entry.")
        self.assertTrue(AuditLog.objects.filter(action="POST_REVIEW_REJECTED").exists())

    def test_approve_marks_post_verified(self):
        _, _, _, post, _ = make_reward("post-3")
        SocialPost.objects.filter(pk=post.pk).update(
            verification_status=PostVerificationStatus.SUSPICIOUS_ACTIVITY,
            rejection_reason="Flagged earlier.",
        )

        response = self.client.post(
            f"/api/v1/admin/posts/{post.pk}/review/", {"decision": "approve"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["verification_status"], PostVerificationStatus.VERIFIED)
        self.assertEqual(response.data["rejection_reason"], "")

    def test_unknown_decision_is_rejected(self):
        _, _, _, post, _ = make_reward("post-4")
        response = self.client.post(
            f"/api/v1/admin/posts/{post.pk}/review/", {"decision": "shrug"}, format="json"
        )
        self.assertEqual(response.status_code, 400)


class RewardReviewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=make_staff())

    def test_approve_then_release_reward(self):
        _, _, _, _, reward = make_reward("reward-1")
        approved = self.client.post(
            f"/api/v1/admin/rewards/{reward.pk}/review/", {"decision": "approve"}, format="json"
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.data["status"], RewardStatus.APPROVED)

        released = self.client.post(
            f"/api/v1/admin/rewards/{reward.pk}/review/",
            {"decision": "available"},
            format="json",
        )
        self.assertEqual(released.data["status"], RewardStatus.AVAILABLE)

    def test_reverse_requires_reason_and_restores_budget(self):
        _, _, campaign, _, reward = make_reward("reward-2", budget=Decimal("100"), rate=Decimal("5"))
        campaign.refresh_from_db()
        self.assertEqual(campaign.remaining_budget, Decimal("95"))

        missing = self.client.post(
            f"/api/v1/admin/rewards/{reward.pk}/review/", {"decision": "reverse"}, format="json"
        )
        self.assertEqual(missing.status_code, 400)

        reversed_response = self.client.post(
            f"/api/v1/admin/rewards/{reward.pk}/review/",
            {"decision": "reverse", "reason": "Fraudulent metrics."},
            format="json",
        )
        self.assertEqual(reversed_response.status_code, 200)
        self.assertEqual(reversed_response.data["status"], RewardStatus.REVERSED)
        campaign.refresh_from_db()
        self.assertEqual(campaign.remaining_budget, Decimal("100.000000000000000000"))

    def test_unknown_decision_is_rejected(self):
        _, _, _, _, reward = make_reward("reward-3")
        response = self.client.post(
            f"/api/v1/admin/rewards/{reward.pk}/review/", {"decision": "ignore"}, format="json"
        )
        self.assertEqual(response.status_code, 400)


def make_claim(external_id="claim-1"):
    """A CREATED/SIGNING claim for an AVAILABLE reward."""
    user, profile, campaign, post, reward = make_reward(external_id)
    make_token_config(symbol="TST")
    approve_reward(reward, actor=user)
    make_available(reward, actor=user)
    reward.refresh_from_db()
    wallet = make_verified_wallet(profile, address=WALLET)
    claim = create_claim(profile, wallet, reward, actor=user)
    return user, profile, reward, claim


class ClaimAdminTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=make_staff())

    def test_claim_directory_filters_by_status(self):
        _, _, _, claim = make_claim("claim-2")
        response = self.client.get("/api/v1/admin/claims/", {"status": claim.status})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

        none = self.client.get("/api/v1/admin/claims/", {"status": "CONFIRMED"})
        self.assertEqual(none.data["count"], 0)

    def test_failing_a_claim_requires_a_reason(self):
        _, _, _, claim = make_claim("claim-3")
        response = self.client.post(f"/api/v1/admin/claims/{claim.pk}/fail/", {}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_failing_a_claim_is_audited_and_keeps_the_reward_claimable(self):
        _, _, reward, claim = make_claim("claim-4")
        response = self.client.post(
            f"/api/v1/admin/claims/{claim.pk}/fail/",
            {"reason": "Transaction reverted (out of gas)."},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], ClaimStatus.FAILED)
        self.assertEqual(response.data["failure_reason"], "Transaction reverted (out of gas).")
        self.assertTrue(AuditLog.objects.filter(action="CLAIM_FAILED").exists())

        reward.refresh_from_db()
        self.assertEqual(reward.status, RewardStatus.AVAILABLE)


class RiskQueueApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=make_staff())

    def test_queue_is_empty_by_default(self):
        response = self.client.get("/api/v1/admin/risk/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(response.data["summary"]["open"], 0)

    def test_resolving_a_flag_requires_a_valid_decision(self):
        _, profile = make_user()
        flag = risk.queue_flag(
            "SELLER",
            profile.pk,
            seller=profile,
            signals=[{"signal": "unusual_claim_volume", "weight": 40, "detail": {}}],
        )
        bad = self.client.post(
            f"/api/v1/admin/risk/{flag.pk}/resolve/", {"decision": "punish"}, format="json"
        )
        self.assertEqual(bad.status_code, 400)

    def test_dismissing_a_flag_removes_it_from_the_open_queue(self):
        _, profile = make_user()
        flag = risk.queue_flag(
            "SELLER",
            profile.pk,
            seller=profile,
            signals=[{"signal": "unusual_claim_volume", "weight": 40, "detail": {}}],
        )
        response = self.client.post(
            f"/api/v1/admin/risk/{flag.pk}/resolve/",
            {"decision": "dismiss", "note": "Verified manually."},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], RiskStatus.DISMISSED)
        self.assertEqual(risk.open_flags().count(), 0)
        self.assertEqual(RiskFlag.objects.filter(status=RiskStatus.DISMISSED).count(), 1)


class AuditLogApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.staff = make_staff()
        self.client.force_authenticate(user=self.staff)

    def test_audit_log_lists_sensitive_actions(self):
        _, _, _, _, reward = make_reward("audit-1")
        self.client.post(
            f"/api/v1/admin/rewards/{reward.pk}/review/", {"decision": "approve"}, format="json"
        )

        response = self.client.get("/api/v1/admin/audit-logs/", {"action": "REWARD_APPROVED"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        entry = response.data["results"][0]
        self.assertEqual(entry["action"], "REWARD_APPROVED")
        self.assertEqual(entry["actor"], self.staff.get_username())
        self.assertEqual(entry["object_type"], "Reward")
        self.assertEqual(entry["object_id"], str(reward.pk))

    def test_audit_log_can_be_filtered_by_object(self):
        _, _, _, _, reward = make_reward("audit-2")
        response = self.client.get(
            "/api/v1/admin/audit-logs/", {"object_type": "Reward", "object_id": reward.pk}
        )
        self.assertGreaterEqual(response.data["count"], 1)


class SettingsApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=make_staff())

    def test_settings_expose_controls_tokens_and_risk_config(self):
        make_token_config(symbol="TST")

        response = self.client.get("/api/v1/admin/settings/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["claiming_paused"])
        self.assertEqual(response.data["risk"]["review_threshold"], risk.review_threshold())
        self.assertIn("engagement_spike", response.data["risk"]["signal_weights"])
        self.assertEqual(response.data["counts"]["token_configs"], 1)
        self.assertEqual(response.data["tokens"][0]["symbol"], "TST")