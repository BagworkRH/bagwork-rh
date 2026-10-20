"""Multi-platform provider layer tests (Spec 03).

The point of the platform abstraction is that no single network is load-bearing,
so these tests cover what actually breaks when a second platform exists: id
collisions, per-platform session isolation, and adapter resolution.
"""
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.social.models import SocialAccount, SocialOAuthState, SocialPlatform, SocialPost
from apps.social.providers import (
    REGISTRY,
    available_platforms,
    get_provider,
    is_mock,
    provider_mode,
)
from apps.social.providers.base import SocialProvider, SocialProviderError
from apps.social.providers.official import OfficialXProvider
from apps.social.services import link_social_account
from apps.social.tasks import purge_social_oauth_states

from .helpers import make_user

# A deliberately ambiguous id: every social network hands out long numeric
# strings, so the same digits can legitimately appear on two of them.
AMBIGUOUS_ID = "7123456789012345678"


class ProviderRegistryTests(TestCase):
    def test_x_is_the_only_served_platform(self):
        # TikTok was removed. The API must not advertise a network this build
        # cannot actually connect: a listed platform with no adapter is a
        # capability we claim and cannot honour.
        self.assertEqual(list(REGISTRY), ["x"])
        self.assertEqual(available_platforms(), ["x"])

    def test_the_adapter_implements_the_interface(self):
        # The abstraction is only real if every adapter satisfies it.
        self.assertTrue(issubclass(OfficialXProvider, SocialProvider))
        self.assertTrue(OfficialXProvider.platform)

    def test_unknown_platform_raises_rather_than_defaulting_to_x(self):
        # A typo must not silently route another network's post to X.
        with override_settings(SOCIAL_PROVIDER_MODE="official"):
            with self.assertRaises(SocialProviderError):
                get_provider("myspace")

    def test_mock_mode_resolves_every_registered_platform(self):
        with override_settings(SOCIAL_PROVIDER_MODE="mock"):
            self.assertEqual(provider_mode(), "mock")
            self.assertTrue(is_mock())
            for platform in available_platforms():
                self.assertEqual(get_provider(platform).platform, platform)

    def test_official_mode_resolves_each_registered_adapter(self):
        # Regression: the registry used __import__(".official"), which cannot
        # resolve a leading-dot module, so every official-mode lookup raised
        # ModuleNotFoundError. Mock mode hid it because it imports directly.
        with override_settings(SOCIAL_PROVIDER_MODE="official"):
            for platform in available_platforms():
                provider = get_provider(platform)
                self.assertIsInstance(provider, OfficialXProvider)
                self.assertEqual(provider.platform, platform)

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
            seller=profile, platform=SocialPlatform.INSTAGRAM, external_post_id=AMBIGUOUS_ID,
            post_url=f"https://instagram.com/p/{AMBIGUOUS_ID}",
            published_at=timezone.now(),
        )
        self.assertNotEqual(x_post.pk, tt_post.pk)
        self.assertEqual(SocialPost.objects.count(), 2)

    def test_same_user_id_on_two_platforms_are_distinct_accounts(self):
        user, profile = make_user()
        identity = {"provider_user_id": "42", "username": "alice"}
        x_account = link_social_account(profile, identity, platform=SocialPlatform.X)
        ig_account = link_social_account(profile, identity, platform=SocialPlatform.INSTAGRAM)
        self.assertNotEqual(x_account.pk, ig_account.pk)
        self.assertEqual(SocialAccount.objects.filter(seller=profile).count(), 2)

    def test_seller_can_hold_one_account_per_platform(self):
        user, profile = make_user()
        for platform in (SocialPlatform.X, SocialPlatform.INSTAGRAM):
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
            profile, {"provider_user_id": "1", "username": "a"},
            platform=SocialPlatform.INSTAGRAM,
        )
        x_account.status = "DISCONNECTED"
        x_account.save()
        self.assertEqual(
            SocialAccount.objects.filter(seller=profile, status="CONNECTED").count(), 1
        )


class PlatformScopedOAuthStateTests(TestCase):
    """A callback must never complete an authorization minted elsewhere."""

    def test_callback_url_is_platform_specific(self):
        self.assertIn("/x/callback/", reverse("social:callback", kwargs={"platform": "x"}))

    def test_unserved_platform_has_no_callback(self):
        # The path segment is accepted by the URLconf, but a platform with no
        # adapter has nothing to exchange the code with, so the route 404s
        # rather than pretending to be connectable.
        anon = APIClient()
        resp = anon.get("/api/v1/x/instagram/callback/?state=x&code=c")

        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_state_issued_for_another_platform_is_useless_here(self):
        # Platform is part of the state's identity. The callback looks the state
        # up scoped by platform, so a handle minted for a different network
        # finds nothing and links nothing.
        user, profile = make_user()
        SocialOAuthState.objects.create(
            state="shared-handle",
            platform=SocialPlatform.INSTAGRAM,
            user=user,
            code_verifier="v",
            scopes=["tweet.read"],
            expires_at=timezone.now() + timedelta(minutes=5),
        )

        anon = APIClient()
        resp = anon.get("/api/v1/x/x/callback/?state=shared-handle&code=c")

        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertIn("error=invalid_state", resp["Location"])
        self.assertEqual(SocialAccount.objects.count(), 0)


class OAuthCallbackFlowTests(TestCase):
    """The browser round-trip the SPA actually performs.

    `connect` is authenticated (bearer token); the provider then returns the
    browser to `callback` with no token at all. These tests pin that down: the
    callback works anonymously, and `state` is what links the account.
    """

    def setUp(self):
        self.client = APIClient()
        self.user, self.profile = make_user()
        self.client.force_authenticate(self.user)

    def _connect(self, platform="x"):
        with override_settings(SOCIAL_PROVIDER_MODE="mock"):
            resp = self.client.post(f"/api/v1/x/{platform}/connect/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return parse_qs(urlparse(resp.data["authorize_url"]).query)["state"][0]

    def test_callback_links_the_account_without_a_token(self):
        state = self._connect()

        # A brand-new client: no credentials, exactly like the provider redirect.
        anon = APIClient()
        with override_settings(SOCIAL_PROVIDER_MODE="mock"):
            resp = anon.get(f"/api/v1/x/x/callback/?state={state}&code=mock-code")

        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertIn("connected=x", resp["Location"])
        self.assertEqual(
            SocialAccount.objects.filter(
                seller=self.profile, platform=SocialPlatform.X
            ).count(),
            1,
        )

    def test_state_is_single_use(self):
        state = self._connect()
        anon = APIClient()
        with override_settings(SOCIAL_PROVIDER_MODE="mock"):
            first = anon.get(f"/api/v1/x/x/callback/?state={state}&code=c")
            second = anon.get(f"/api/v1/x/x/callback/?state={state}&code=c")

        self.assertIn("connected=x", first["Location"])
        self.assertIn("error=invalid_state", second["Location"])

    def test_expired_state_is_rejected(self):
        state = self._connect()
        SocialOAuthState.objects.filter(state=state).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        anon = APIClient()
        resp = anon.get(f"/api/v1/x/x/callback/?state={state}&code=c")

        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertIn("error=invalid_state", resp["Location"])
        self.assertEqual(SocialAccount.objects.count(), 0)

    def test_unknown_state_is_rejected(self):
        anon = APIClient()
        resp = anon.get("/api/v1/x/x/callback/?state=nope&code=c")

        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertIn("error=invalid_state", resp["Location"])

    def test_connect_records_a_pending_state(self):
        state = self._connect("x")

        pending = SocialOAuthState.objects.get(state=state)
        self.assertEqual(pending.platform, SocialPlatform.X)
        self.assertEqual(pending.user, self.user)
        self.assertTrue(pending.is_usable())

    def test_purge_removes_only_unredeemable_states(self):
        live = self._connect()
        stale = self._connect()
        SocialOAuthState.objects.filter(state=stale).update(
            expires_at=timezone.now() - timedelta(hours=48)
        )

        result = purge_social_oauth_states(older_than_hours=24)

        self.assertEqual(result["status"], "ok")
        self.assertFalse(SocialOAuthState.objects.filter(state=stale).exists())
        self.assertTrue(SocialOAuthState.objects.filter(state=live).exists())

    def test_purge_task_is_scheduled(self):
        from django.conf import settings  # noqa: PLC0415

        entry = settings.CELERY_BEAT_SCHEDULE["purge-social-oauth-states"]
        self.assertEqual(entry["task"], "apps.social.tasks.purge_social_oauth_states")


class PlatformApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user, self.profile = make_user()
        self.client.force_authenticate(self.user)

    def test_list_platforms(self):
        resp = self.client.get("/api/v1/x/platforms/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [p["id"] for p in resp.data["platforms"]]
        self.assertEqual(ids, ["x"])

    def test_list_platforms_is_public(self):
        # Available platforms describe the build, not the caller, and onboarding
        # needs them before anyone has a session; requiring auth left the list
        # empty for the very screen that lists them.
        anonymous = APIClient()
        resp = anonymous.get("/api/v1/x/platforms/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["platforms"])

    def test_connect_accepts_a_platform(self):
        with override_settings(SOCIAL_PROVIDER_MODE="mock"):
            resp = self.client.post("/api/v1/x/x/connect/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["platform"], "x")

    def test_connect_rejects_unknown_platform(self):
        with override_settings(SOCIAL_PROVIDER_MODE="mock"):
            resp = self.client.post("/api/v1/x/myspace/connect/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
