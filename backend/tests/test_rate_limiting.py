"""Rate-limit tests (Spec 05 Phase 8 hardening).

Each test shrinks the throttle rates and clears the shared throttle cache
first, so behaviour is deterministic regardless of test ordering. The default
(dev) rates are deliberately huge so everyday local work and the rest of the
suite never trip 429s.

Shrinking the rates needs two different knobs, because DRF reads them
differently:

* the path-scoped throttles in `config.throttling` resolve their rate from
  `api_settings` on every request, and `api_settings` is reloaded when
  `REST_FRAMEWORK` changes;
* DRF's own `AnonRateThrottle` / `UserRateThrottle` read the
  `THROTTLE_RATES` class attribute that was captured at import time, so that
  has to be patched on the class.

Overriding `DEFAULT_THROTTLE_RATES` directly would do neither.
"""
import contextlib
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from apps.accounts.models import User

TOO_MANY = status.HTTP_429_TOO_MANY_REQUESTS

# Tiny budgets for the path-scoped throttles; the anon/user baselines stay
# generous so they never interfere with the scoped assertions.
# Every scope must be present: `PathScopedThrottle.get_rate` raises
# ImproperlyConfigured for a scope with no rate, and these throttles are already
# captured on `APIView` at import time, so a missing key breaks every request.
TINY_SCOPES = {
    "anon": "1000/hour",
    "user": "1000/hour",
    "auth": "3/hour",
    "admin": "3/hour",
    "wallet": "3/hour",
    "submit": "3/hour",
}
# ...and the inverse: a tiny anonymous baseline with the scopes out of the way.
TINY_ANON = {**TINY_SCOPES, "anon": "2/hour"}


@contextlib.contextmanager
def throttle_rates(rates):
    """Apply `rates` to every throttle for the duration of the block."""
    rest_framework = {**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": rates}
    with override_settings(REST_FRAMEWORK=rest_framework):
        with mock.patch.object(SimpleRateThrottle, "THROTTLE_RATES", rates):
            yield


class RateLimitingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def assertThrottled(self, url, method="get", attempts=3, **kwargs):
        """Assert `attempts` requests pass and the next one is a 429."""
        for _ in range(attempts):
            resp = getattr(self.client, method)(url, **kwargs)
            self.assertNotEqual(resp.status_code, TOO_MANY, resp.data)
        resp = getattr(self.client, method)(url, **kwargs)
        self.assertEqual(resp.status_code, TOO_MANY)
        return resp

    def test_auth_scope_throttles_register(self):
        with throttle_rates(TINY_SCOPES):
            resp = self.assertThrottled(
                "/api/v1/auth/register/", method="post", format="json", data={}
            )
        self.assertIn("throttled", resp.data["detail"].lower())

    def test_admin_scope_throttles_staff_api(self):
        ops = User.objects.create_superuser(
            username="ops", email="ops@example.com", password="x" * 20
        )
        self.client.force_authenticate(user=ops)
        with throttle_rates(TINY_SCOPES):
            self.assertThrottled("/api/v1/admin/overview/")

    def test_wallet_scope_throttles_claim_mutations(self):
        user = User.objects.create_user(
            username="seller1", email="seller1@example.com", password="x" * 20
        )
        self.client.force_authenticate(user=user)
        with throttle_rates(TINY_SCOPES):
            self.assertThrottled(
                "/api/v1/claims/", method="post", format="json", data={}
            )

    def test_wallet_scope_throttles_authorization_read(self):
        # The EIP-712 authorization GET signs payloads, so it is throttled too.
        user = User.objects.create_user(
            username="seller2", email="seller2@example.com", password="x" * 20
        )
        self.client.force_authenticate(user=user)
        with throttle_rates(TINY_SCOPES):
            self.assertThrottled("/api/v1/claims/1/authorization/")

    def test_baseline_anon_throttle_applies_everywhere(self):
        with throttle_rates(TINY_ANON):
            self.assertThrottled("/api/health/", attempts=2)

    def test_reads_outside_scoped_paths_are_not_blocked(self):
        # Authenticated reads outside every scoped path must pass at the tiny
        # scoped budgets (only the generous 'user' baseline applies).
        user = User.objects.create_user(
            username="seller3", email="seller3@example.com", password="x" * 20
        )
        self.client.force_authenticate(user=user)
        with throttle_rates(TINY_SCOPES):
            for _ in range(25):
                resp = self.client.get("/api/v1/me/")
                self.assertNotEqual(resp.status_code, TOO_MANY)
            # Plain claim reads are not mutations and must stay unthrottled.
            for _ in range(10):
                resp = self.client.get("/api/v1/claims/1/")
                self.assertNotEqual(resp.status_code, TOO_MANY)

    def test_missing_scope_rate_fails_loudly(self):
        user = User.objects.create_user(
            username="seller4", email="seller4@example.com", password="x" * 20
        )
        self.client.force_authenticate(user=user)
        rates = {key: value for key, value in TINY_SCOPES.items() if key != "wallet"}
        with throttle_rates(rates):
            # A typo in THROTTLE_* must not silently disable a limit.
            with self.assertRaises(ImproperlyConfigured):
                self.client.get("/api/v1/claims/1/authorization/")