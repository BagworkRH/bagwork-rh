"""Retention and erasure of platform-derived content (docs/10).

The X data-use note promises a retention period and a deletion route. These tests
hold the two things that promise rests on: that the content really does go, and
that the financial records sitting next to it survive — because `Reward.post` is
PROTECT, and getting this wrong either destroys the audit trail or leaves the
platform's data behind.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.rewards.models import Reward, RewardStatus
from apps.social.erasure import ERASED_URL, purge_expired_social_data
from apps.social.models import (
    PostMetricSnapshot,
    SocialOAuthState,
    SocialPlatform,
    SocialPost,
)
from apps.social.services import link_social_account

from .helpers import make_campaign, make_post, make_user

User = get_user_model()


class RetentionPurgeTests(TestCase):
    def setUp(self):
        self.user, self.profile = make_user()
        now = timezone.now()
        # A campaign that finished well outside the window.
        self.old_campaign = make_campaign(
            name="Old", slug="old", start_at=now - timedelta(days=500),
            end_at=now - timedelta(days=400),
        )
        self.post = make_post(self.profile, self.old_campaign, "1", text="#ad hello")
        self.post.impressions = 500
        self.post.likes = 12
        self.post.save(update_fields=["impressions", "likes"])
        PostMetricSnapshot.objects.create(
            post=self.post, impressions=500, raw_provider_payload={"id": "1", "text": "x"}
        )

    def test_erases_the_content_after_the_window(self):
        result = purge_expired_social_data(retention_days=365)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["erased"], 1)

        self.post.refresh_from_db()
        self.assertEqual(self.post.text_snapshot, "")
        self.assertEqual(self.post.post_url, ERASED_URL)
        self.assertEqual(self.post.external_post_id, f"erased-{self.post.pk}")
        self.assertEqual(self.post.impressions, 0)
        self.assertEqual(self.post.likes, 0)
        self.assertIsNotNone(self.post.erased_at)

    def test_deletes_the_metric_snapshots_that_carry_raw_payloads(self):
        purge_expired_social_data(retention_days=365)

        self.assertEqual(PostMetricSnapshot.objects.filter(post=self.post).count(), 0)

    def test_leaves_a_campaign_that_ended_recently_alone(self):
        recent = make_campaign(name="Recent", slug="recent")
        fresh = make_post(self.profile, recent, "2", text="still live")

        purge_expired_social_data(retention_days=365)

        fresh.refresh_from_db()
        self.assertEqual(fresh.text_snapshot, "still live")
        self.assertIsNone(fresh.erased_at)

    def test_the_post_and_its_reward_survive(self):
        # The whole point: the X data goes, the money record stays. Deleting the
        # row would raise ProtectedError, which is why erasure anonymises.
        reward = Reward.objects.create(
            seller=self.profile, campaign=self.old_campaign, post=self.post,
            amount=Decimal("1"), gross_amount=Decimal("1"),
            token_symbol="USDG", chain_id=46630, status=RewardStatus.AVAILABLE,
        )

        purge_expired_social_data(retention_days=365)

        reward.refresh_from_db()
        self.assertTrue(SocialPost.objects.filter(pk=self.post.pk).exists())
        self.assertEqual(reward.amount, Decimal("1"))
        self.assertEqual(reward.status, RewardStatus.AVAILABLE)

    def test_is_idempotent(self):
        first = purge_expired_social_data(retention_days=365)
        second = purge_expired_social_data(retention_days=365)

        self.assertEqual(first["erased"], 1)
        self.assertEqual(second["erased"], 0)

    def test_erases_an_old_post_that_belongs_to_no_campaign(self):
        orphan = SocialPost.objects.create(
            seller=self.profile, platform=SocialPlatform.X, external_post_id="3",
            post_url="https://x.com/status/3", text_snapshot="orphan",
            published_at=timezone.now() - timedelta(days=400),
            discovered_at=timezone.now() - timedelta(days=400),
        )

        purge_expired_social_data(retention_days=365)

        orphan.refresh_from_db()
        self.assertEqual(orphan.text_snapshot, "")
        self.assertIsNotNone(orphan.erased_at)

    def test_the_purge_task_is_scheduled(self):
        from django.conf import settings  # noqa: PLC0415

        entry = settings.CELERY_BEAT_SCHEDULE["purge-expired-social-data"]
        self.assertEqual(entry["task"], "apps.social.tasks.purge_expired_social_data")


@override_settings(SOCIAL_PROVIDER_MODE="mock")
class DataDeletionEndpointTests(TestCase):
    """`POST /me/data-deletion/`.

    Mock provider mode because erasure revokes the stored token at the platform,
    and a test must not make that call for real.
    """

    def setUp(self):
        self.client = APIClient()
        self.user, self.profile = make_user()
        self.client.force_authenticate(self.user)
        self.campaign = make_campaign()
        self.post = make_post(self.profile, self.campaign, "1", text="#ad hello")
        self.post.impressions = 500
        self.post.save(update_fields=["impressions"])
        self.account = link_social_account(
            self.profile,
            {"provider_user_id": "42", "username": "creator", "access_token": "tok"},
            platform=SocialPlatform.X,
        )
        SocialOAuthState.objects.create(
            state="s1", platform=SocialPlatform.X, user=self.user,
            code_verifier="v", scopes=["tweet.read"],
            expires_at=timezone.now() + timedelta(minutes=5),
        )

    def _delete(self, **body):
        return self.client.post(
            "/api/v1/me/data-deletion/", body or {"confirm": "DELETE"}, format="json"
        )

    def test_erases_the_sellers_platform_data(self):
        resp = self._delete()

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["posts_erased"], 1)
        self.assertEqual(resp.data["accounts_erased"], 1)

        self.post.refresh_from_db()
        self.assertEqual(self.post.text_snapshot, "")
        self.assertIsNotNone(self.post.erased_at)

        self.account.refresh_from_db()
        self.assertEqual(self.account.status, "DISCONNECTED")
        self.assertEqual(bytes(self.account.encrypted_credentials), b"")
        self.assertTrue(self.account.username.startswith("erased-"))

        self.assertEqual(SocialOAuthState.objects.filter(user=self.user).count(), 0)

    def test_anonymises_the_account_but_keeps_the_row(self):
        self._delete()

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertIn("erased.invalid", self.user.email)
        self.assertTrue(self.user.username.startswith("deleted-"))
        self.assertFalse(self.user.has_usable_password())
        # The row survives so the ledger's foreign keys stay intact.
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_keeps_financial_records(self):
        reward = Reward.objects.create(
            seller=self.profile, campaign=self.campaign, post=self.post,
            amount=Decimal("2"), gross_amount=Decimal("2"),
            token_symbol="USDG", chain_id=46630, status=RewardStatus.APPROVED,
        )

        self._delete()

        reward.refresh_from_db()
        self.assertEqual(reward.amount, Decimal("2"))
        self.assertEqual(reward.status, RewardStatus.APPROVED)

    def test_writes_an_audit_entry(self):
        self._delete()

        entry = AuditLog.objects.filter(action="SELLER_DATA_ERASED").first()
        self.assertIsNotNone(entry)
        self.assertTrue(entry.metadata["financial_records_retained"])

    def test_the_users_token_stops_working(self):
        token = Token.objects.create(user=self.user)

        self._delete()

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        self.assertEqual(client.get("/api/v1/me/").status_code, status.HTTP_401_UNAUTHORIZED)

    def test_requires_explicit_confirmation(self):
        resp = self._delete(confirm="yes")

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.post.refresh_from_db()
        self.assertIsNone(self.post.erased_at)

    def test_requires_authentication(self):
        resp = APIClient().post(
            "/api/v1/me/data-deletion/", {"confirm": "DELETE"}, format="json"
        )

        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_leaves_another_seller_alone(self):
        other_user, other_profile = make_user(email="other@example.com", username="other")
        other_post = make_post(other_profile, self.campaign, "9", text="not mine")

        self._delete()

        other_post.refresh_from_db()
        self.assertEqual(other_post.text_snapshot, "not mine")
        other_user.refresh_from_db()
        self.assertTrue(other_user.is_active)

