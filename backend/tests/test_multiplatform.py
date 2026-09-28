"""Multi-platform provider layer tests (Spec 03).

The point of the platform abstraction is that no single network is load-bearing,
so these tests cover what actually breaks when a second platform exists: id
collisions, per-platform session isolation, and adapter resolution.
"""
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.social.models import SocialAccount, SocialPlatform, SocialPost
from apps.social.providers import (
    REGISTRY,
    available_platforms,
    get_provider,
    is_mock,
    provider_mode,
)
from apps.social.providers.base import SocialProvider, SocialProviderError
from apps.social.providers.official import OfficialXProvider
from apps.social.providers.tiktok import OfficialTikTokProvider
from apps.social.services import link_social_account

from .helpers import make_user

# A deliberately ambiguous id: X and TikTok both hand out long numeric strings.
AMBIGUOUS_ID = "7123456789012345678"


class ProviderRegistryTests(TestCase):
    def test_x_and_tiktok_are_registered(self):
        self.assertIn("x", REGISTRY)
        self.assertIn("tiktok", REGISTRY)
        self.assertIn("x", available_platforms())
        self.assertIn("tiktok", available_platforms())

    def test_both_adapters_implement_the_interface(self):
        # The abstraction is only real if every adapter satisfies it.
        for cls in (OfficialXProvider, OfficialTikTokProvider):
            self.assertTrue(issubclass(cls, SocialProvider))
            self.assertTrue(cls.platform)

    def test_unknown_platform_raises_rather_than_defaulting_to_x(self):
        # A typo must not silently route a TikTok post to X.
        with override_settings(SOCIAL_PROVIDER_MODE="official"):
            with self.assertRaises(SocialProviderError):
                get_provider("myspace")

    def test_mock_mode_resolves_every_registered_platform(self):
        with override_settings(SOCIAL_PROVIDER_MODE="mock"):
            self.assertEqual(provider_mode(), "mock")
            self.assertTrue(is_mock())
            for platform in available_platforms():
                self.assertEqual(get_provider(platform).platform, platform)

    def test_legacy_x_provider_setting_still_works(self):
        # Backwards compatibility: X_PROVIDER=mock predates SOCIAL_PROVIDER_MODE.
        with override_settings(SOCIAL_PROVIDER_MODE="", X_PROVIDER="mock"):
            self.assertEqual(provider_mode(), "mock")


class PlatformIdentityTests(TestCase):
    def test_same_post_id_on_two_platforms_are_distinct_posts(self):
        user, profile = make_user()
        x_post = SocialPost.objects.create(
            seller=profile, platform=SocialPlatform.X, external_post_id=AMBIGUOUS_ID,
            post_url=f"https://x.com/a/status/{AMBIGUOUS_ID}",
            published_at=timezone.now(),
        )
        tt_post = SocialPost.objects.create(
            seller=profile, platform=SocialPlatform.TIKTOK, external_post_id=AMBIGUOUS_ID,
            post_url=f"https://tiktok.com/@a/video/{AMBIGUOUS_ID}",
            published_at=timezone.now(),
        )
        self.assertNotEqual(x_post.pk, tt_post.pk)
        self.assertEqual(SocialPost.objects.count(), 2)

    def test_same_user_id_on_two_platforms_are_distinct_accounts(self):
        user, profile = make_user()
        identity = {"provider_user_id": "42", "username": "alice"}
        x_account = link_social_account(profile, identity, platform=SocialPlatform.X)
        tt_account = link_social_account(profile, identity, platform=SocialPlatform.TIKTOK)
        self.assertNotEqual(x_account.pk, tt_account.pk)
        self.assertEqual(SocialAccount.objects.filter(seller=profile).count(), 2)

    def test_seller_can_hold_one_account_per_platform(self):
        user, profile = make_user()
        for platform in (SocialPlatform.X, SocialPlatform.TIKTOK):
            SocialAccount.objects.create(
                seller=profile, platform=platform, provider_user_id="1", username="alice"
            )
        self.assertEqual(SocialAccount.objects.filter(seller=profile).count(), 2)

    def test_disconnecting_one_platform_leaves_the_other(self):
        user, profile = make_user()
        x_account = link_social_account(
            profile, {"provider_user_id": "1", "username": "a"}, platform=SocialPlatform.X
        )
        link_social_account(
            profile, {"provider_user_id": "1", "username": "a"}, platform=SocialPlatform.TIKTOK
        )
        x_account.status = "DISCONNECTED"
        x_account.save()
        self.assertEqual(
            SocialAccount.objects.filter(seller=profile, status="CONNECTED").count(), 1
        )


class PlatformScopedSessionTests(TestCase):
    """An X callback must never complete a TikTok authorization."""

    def test_session_keys_are_namespaced_per_platform(self):
        x_key = OfficialXProvider()._session_key("state")
        tt_key = OfficialTikTokProvider()._session_key("state")
        self.assertNotEqual(x_key, tt_key)
        self.assertIn("x", x_key)
        self.assertIn("tiktok", tt_key)

    def test_callback_url_is_platform_specific(self):
        self.assertIn("/x/callback/", reverse("social:callback", kwargs={"platform": "x"}))
        self.assertIn(
            "/tiktok/callback/", reverse("social:callback", kwargs={"platform": "tiktok"})
        )


class PlatformApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user, self.profile = make_user()
        self.client.force_authenticate(self.user)

    def test_list_platforms(self):
        resp = self.client.get("/api/v1/x/platforms/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [p["id"] for p in resp.data["platforms"]]
        self.assertIn("x", ids)
        self.assertIn("tiktok", ids)

    def test_connect_accepts_a_platform(self):
        with override_settings(SOCIAL_PROVIDER_MODE="mock"):
            resp = self.client.post("/api/v1/x/x/connect/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["platform"], "x")

    def test_connect_rejects_unknown_platform(self):
        with override_settings(SOCIAL_PROVIDER_MODE="mock"):
            resp = self.client.post("/api/v1/x/myspace/connect/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
