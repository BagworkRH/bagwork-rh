"""X OAuth token renewal (Spec 03).

Every linked account hit `Timeline fetch failed: HTTP 401` because the connect
flow asked for `tweet.read` and `users.read` only. Without `offline.access` X
issues no refresh token, so nothing could renew an access token that expires
after about two hours -- and the code read a `refresh_token` that was never
granted. These tests pin the fix: the scope is requested, a 401 is treated as
renewable rather than fatal, and the rotated credentials are persisted before
they are needed again.
"""
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.social.crypto_utils import encrypt_secret
from apps.social.models import SocialAccount, SocialPlatform
from apps.social.providers.base import SocialProviderAuthError, SocialProviderError
from apps.social.providers.official import OfficialXProvider
from apps.social.services import (
    REFRESH_MARGIN,
    STATUS_REAUTH_REQUIRED,
    load_credentials,
    refresh_account_credentials,
    store_credentials,
    token_needs_refresh,
    with_fresh_token,
)
from apps.social.tasks import discover_posts_for_account
from apps.social.views import REQUIRED_SCOPES

from .helpers import make_campaign, make_user


def _provider():
    """The real adapter with credentials injected, so no settings are needed."""
    return OfficialXProvider(
        client_id="client-id",
        client_secret="client-secret",
        redirect_uri="https://example.test/social/x/callback/",
    )


def _response(ok=True, status_code=200, payload=None):
    """Minimal stand-in for a requests.Response (the shape test_discovery uses)."""
    return SimpleNamespace(ok=ok, status_code=status_code, json=lambda: payload or {})


class RequestedScopeTests(TestCase):
    def test_x_connect_asks_for_offline_access(self):
        # The root cause of the production 401s. Without this scope X returns no
        # refresh token at all, so there is nothing to renew with and every
        # account stops working two hours after it is connected.
        self.assertIn("offline.access", REQUIRED_SCOPES[SocialPlatform.X])


class RefreshGrantTests(TestCase):
    """The refresh grant itself, against a faked transport."""

    def test_sends_refresh_grant_and_returns_rotated_pair(self):
        with mock.patch(
            "apps.social.providers.official.requests.post",
            return_value=_response(
                payload={"access_token": "new", "refresh_token": "new-r", "expires_in": 7200}
            ),
        ) as post:
            result = _provider().refresh_access_token("old-r")

        sent = post.call_args.kwargs["data"]
        self.assertEqual(sent["grant_type"], "refresh_token")
        self.assertEqual(sent["refresh_token"], "old-r")
        self.assertEqual(sent["client_id"], "client-id")
        self.assertEqual(result["access_token"], "new")
        self.assertEqual(result["refresh_token"], "new-r")
        # expires_in becomes an absolute time, so the next poll can renew before
        # the token dies rather than after the first 401 of a run.
        self.assertGreater(result["expires_at"], timezone.now())

    def test_missing_refresh_token_asks_for_reconnection(self):
        # The state every production account is in right now: connected before
        # offline.access existed, so there is no refresh token to spend.
        with self.assertRaises(SocialProviderAuthError) as ctx:
            _provider().refresh_access_token("")
        self.assertIn("reconnected", str(ctx.exception))

    def test_rejected_refresh_token_is_terminal(self):
        with mock.patch(
            "apps.social.providers.official.requests.post",
            return_value=_response(ok=False, status_code=400),
        ):
            with self.assertRaises(SocialProviderAuthError):
                _provider().refresh_access_token("stale-r")

    def test_omitted_rotated_token_is_reported_as_absent(self):
        # X does not always rotate. The service keeps the stored token in that
        # case, which it can only do if the absence is visible here.
        with mock.patch(
            "apps.social.providers.official.requests.post",
            return_value=_response(payload={"access_token": "new"}),
        ):
            result = _provider().refresh_access_token("old-r")
        self.assertEqual(result["refresh_token"], "")
        self.assertIsNone(result["expires_at"])


class AuthErrorClassificationTests(TestCase):
    """Only a 401 may trigger a refresh: it is the one error a refresh can fix."""

    def test_timeline_401_is_renewable(self):
        with mock.patch(
            "apps.social.providers.official.requests.get",
            return_value=_response(ok=False, status_code=401),
        ):
            with self.assertRaises(SocialProviderAuthError) as ctx:
                _provider()._get_timeline("tok", "42", {})
        # The message operators and existing logs already read is unchanged.
        self.assertIn("Timeline fetch failed: HTTP 401", str(ctx.exception))

    def test_timeline_500_is_not_renewable(self):
        with mock.patch(
            "apps.social.providers.official.requests.get",
            return_value=_response(ok=False, status_code=500),
        ):
            with self.assertRaises(SocialProviderError) as ctx:
                _provider()._get_timeline("tok", "42", {})
        self.assertNotIsInstance(ctx.exception, SocialProviderAuthError)
        self.assertIn("Timeline fetch failed: HTTP 500", str(ctx.exception))

    def test_account_and_post_fetches_keep_their_messages(self):
        for method, args, expected in (
            ("get_account", ("tok",), "Account fetch failed: HTTP 403"),
            ("get_post", ("tok", "1"), "Post fetch failed: HTTP 403"),
        ):
            with mock.patch(
                "apps.social.providers.official.requests.get",
                return_value=_response(ok=False, status_code=403),
            ):
                with self.assertRaises(SocialProviderError) as ctx:
                    getattr(_provider(), method)(*args)
            self.assertEqual(str(ctx.exception), expected)


class CredentialStorageTests(TestCase):
    def setUp(self):
        self.user, self.profile = make_user()
        self.account = SocialAccount.objects.create(
            seller=self.profile,
            platform=SocialPlatform.X,
            provider_user_id="42",
            username="alice",
            status="CONNECTED",
        )

    def test_store_and_load_round_trip(self):
        store_credentials(self.account, access_token="a", refresh_token="r")
        self.assertEqual(
            load_credentials(self.account), {"access_token": "a", "refresh_token": "r"}
        )

    def test_missing_refresh_token_keeps_the_stored_one(self):
        # Overwriting a live refresh token with "" would strand the account at
        # its next expiry, with no way back except a manual reconnect.
        store_credentials(self.account, access_token="a", refresh_token="keep-me")
        store_credentials(self.account, access_token="b", refresh_token="")
        creds = load_credentials(self.account)
        self.assertEqual(creds["access_token"], "b")
        self.assertEqual(creds["refresh_token"], "keep-me")

    def test_credentials_are_encrypted_at_rest(self):
        store_credentials(self.account, access_token="super-secret", refresh_token="r")
        self.assertNotIn(b"super-secret", bytes(self.account.encrypted_credentials))

    def test_unreadable_credentials_are_reported_as_absent(self):
        # A key change without `rotate_social_credentials` makes every blob
        # undecryptable. That must not take a whole discovery run down.
        ciphertext, _iv = encrypt_secret('{"access_token": "a"}')
        self.account.encrypted_credentials = ciphertext
        self.account.credentials_iv = b"\x00" * 12
        self.account.save(update_fields=["encrypted_credentials", "credentials_iv"])
        self.assertEqual(load_credentials(self.account), {})


class TokenRefreshServiceTests(TestCase):
    def setUp(self):
        self.user, self.profile = make_user()
        self.account = SocialAccount.objects.create(
            seller=self.profile,
            platform=SocialPlatform.X,
            provider_user_id="42",
            username="alice",
            status="CONNECTED",
        )
        store_credentials(self.account, access_token="old-access", refresh_token="old-refresh")

    def _provider(self):
        provider = mock.Mock()
        provider.refresh_access_token.return_value = {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_at": timezone.now() + timedelta(hours=2),
        }
        return provider

    def test_expiry_is_recorded_so_renewal_can_be_proactive(self):
        self.account.token_expiry = timezone.now() + timedelta(hours=1)
        self.assertFalse(token_needs_refresh(self.account))
        self.account.token_expiry = timezone.now() + REFRESH_MARGIN - timedelta(seconds=30)
        self.assertTrue(token_needs_refresh(self.account))
        self.account.token_expiry = timezone.now() - timedelta(minutes=1)
        self.assertTrue(token_needs_refresh(self.account))
        # No expiry recorded (a connection made before we stored one) must not
        # look like an expired token, or every call would renew a working one.
        self.account.token_expiry = None
        self.assertFalse(token_needs_refresh(self.account))

    def test_refresh_persists_rotated_credentials_and_audits(self):
        with mock.patch("apps.social.services.get_provider", return_value=self._provider()):
            token = refresh_account_credentials(self.account)

        self.assertEqual(token, "new-access")
        creds = load_credentials(self.account)
        self.assertEqual(creds["access_token"], "new-access")
        # The rotated refresh token must be stored: X kills the one just spent.
        self.assertEqual(creds["refresh_token"], "new-refresh")
        self.assertIsNotNone(self.account.token_expiry)
        self.assertTrue(AuditLog.objects.filter(action="SOCIAL_TOKEN_REFRESHED").exists())

    def test_with_fresh_token_retries_once_after_a_401(self):
        seen = []

        def call(token):
            seen.append(token)
            if token == "old-access":
                raise SocialProviderAuthError("Timeline fetch failed: HTTP 401")
            return "posts"

        with mock.patch("apps.social.services.get_provider", return_value=self._provider()):
            self.assertEqual(with_fresh_token(self.account, call), "posts")
        self.assertEqual(seen, ["old-access", "new-access"])

    def test_with_fresh_token_renews_before_the_call_when_expiry_is_near(self):
        self.account.token_expiry = timezone.now() + timedelta(minutes=1)
        self.account.save(update_fields=["token_expiry"])
        seen = []
        provider = self._provider()

        with mock.patch("apps.social.services.get_provider", return_value=provider):
            with_fresh_token(self.account, seen.append)

        # The almost-expired token is never offered to X at all.
        self.assertEqual(seen, ["new-access"])
        self.assertEqual(provider.refresh_access_token.call_count, 1)

    def test_a_rejected_refresh_marks_the_account_for_reconnection(self):
        provider = mock.Mock()
        provider.refresh_access_token.side_effect = SocialProviderAuthError(
            "Token refresh failed: HTTP 400 (reconnect required)"
        )

        def call(token):
            raise SocialProviderAuthError("Timeline fetch failed: HTTP 401")

        with mock.patch("apps.social.services.get_provider", return_value=provider):
            with self.assertRaises(SocialProviderAuthError):
                with_fresh_token(self.account, call)

        self.account.refresh_from_db()
        # Polling must stop. This token will never work again, and re-asking X
        # once per tick would be a permanent failure nobody is told about.
        self.assertEqual(self.account.status, STATUS_REAUTH_REQUIRED)
        self.assertTrue(
            AuditLog.objects.filter(action="SOCIAL_ACCOUNT_REAUTH_REQUIRED").exists()
        )

    def test_a_successful_renewal_clears_the_reconnection_flag(self):
        self.account.status = STATUS_REAUTH_REQUIRED
        self.account.save(update_fields=["status"])
        with mock.patch("apps.social.services.get_provider", return_value=self._provider()):
            refresh_account_credentials(self.account)
        self.account.refresh_from_db()
        self.assertEqual(self.account.status, "CONNECTED")

    def test_provider_without_refresh_support_is_not_a_broken_account(self):
        # The development mock has no token endpoint. Flagging the account would
        # be a lie about an account that is fine.
        provider = mock.Mock(spec=["get_metrics"])
        with mock.patch("apps.social.services.get_provider", return_value=provider):
            with self.assertRaises(SocialProviderError):
                refresh_account_credentials(self.account)
        self.account.refresh_from_db()
        self.assertEqual(self.account.status, "CONNECTED")


class DiscoveryRenewalTests(TestCase):
    """The path that actually failed in production, end to end."""

    def setUp(self):
        self.user, self.profile = make_user()
        self.campaign = make_campaign(slug="refresh-discovery")
        self.account = SocialAccount.objects.create(
            seller=self.profile,
            platform=SocialPlatform.X,
            provider_user_id="42",
            username="alice",
            status="CONNECTED",
        )
        store_credentials(self.account, access_token="old-access", refresh_token="old-refresh")
        self.posted_at = timezone.now() - timedelta(hours=1)

    def _provider(self, posts):
        provider = mock.Mock()
        provider.refresh_access_token.return_value = {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_at": timezone.now() + timedelta(hours=2),
        }

        def discover(token, *args, **kwargs):
            if token == "old-access":
                raise SocialProviderAuthError("Timeline fetch failed: HTTP 401")
            return posts

        provider.discover_posts.side_effect = discover
        return provider

    def _run_discovery(self, provider):
        # get_provider is imported inside the task *and* inside the service, so
        # both registry lookups have to answer with the same fake.
        with (
            mock.patch("apps.social.providers.get_provider", return_value=provider),
            mock.patch("apps.social.services.get_provider", return_value=provider),
        ):
            return discover_posts_for_account.apply(
                args=[self.account.pk, self.campaign.pk]
            ).get()

    def test_discovery_renews_and_still_records_the_post(self):
        provider = self._provider(
            [{"post_id": "111", "text": "original #ad", "created_at": self.posted_at}]
        )
        result = self._run_discovery(provider)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["created"], 1)
        self.account.refresh_from_db()
        # The rotation was persisted, so the next tick starts from a live token.
        self.assertEqual(load_credentials(self.account)["access_token"], "new-access")

    def test_discovery_reports_reconnection_when_renewal_fails(self):
        provider = mock.Mock()
        provider.refresh_access_token.side_effect = SocialProviderAuthError("Token refresh failed")
        provider.discover_posts.side_effect = SocialProviderAuthError(
            "Timeline fetch failed: HTTP 401"
        )
        result = self._run_discovery(provider)

        self.assertEqual(result["status"], "reauth-required")
        self.account.refresh_from_db()
        self.assertEqual(self.account.status, STATUS_REAUTH_REQUIRED)
