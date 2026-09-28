"""Platform-wide rate limiting (Spec 05 Phase 8 hardening).

The default DRF throttle stack configured in ``REST_FRAMEWORK`` is::

    AdminThrottle  + AuthThrottle  + WalletThrottle
    + AnonRateThrottle + UserRateThrottle

The three scoped classes below are *path-selective*: each only contributes a
bucket when the request targets the sensitive surface it protects (the staff
back-office API, credential endpoints, or wallet/claim signer operations).
Every other request falls straight through to the baseline anonymous /
authenticated limits. This keeps strict limits on the highest-risk endpoints
without touching a single view definition or URL conf.

Rates live in ``REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]`` and are sourced
from the ``THROTTLE_*`` environment variables — see `.env.example`.
"""
from django.core.exceptions import ImproperlyConfigured
from rest_framework.settings import api_settings
from rest_framework.throttling import SimpleRateThrottle


class PathScopedThrottle(SimpleRateThrottle):
    """Per-IP rate limit that only applies to a subset of request paths.

    ``SimpleRateThrottle`` resolves its rate once, from the ``THROTTLE_RATES``
    class attribute that DRF captures at import time. Resolving
    ``api_settings`` on every request instead keeps the rates live, so
    environment changes and ``override_settings`` (tests, staging) take effect
    without the module being reimported.
    """

    scope = ""
    path_prefixes = ()

    def applies_to(self, request):
        """Return True when this throttle should account for the request."""
        return request.path.startswith(self.path_prefixes)

    def get_rate(self):
        try:
            return api_settings.DEFAULT_THROTTLE_RATES[self.scope]
        except KeyError:
            raise ImproperlyConfigured(
                f"No throttle rate configured for the {self.scope!r} scope. "
                "Add it to REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']."
            ) from None

    def get_cache_key(self, request, view):
        # Every scope is keyed per client IP, including authenticated staff:
        # the goal is to blunt credential stuffing and scraping, not to lock a
        # legitimate operator out of their own account.
        ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}

    def allow_request(self, request, view):
        if not self.applies_to(request):
            return True
        return super().allow_request(request, view)


class AdminThrottle(PathScopedThrottle):
    """Strict limit for the staff back-office API (`/api/v1/admin/*`)."""

    scope = "admin"
    path_prefixes = ("/api/v1/admin/",)


class AuthThrottle(PathScopedThrottle):
    """Strict limit for credential endpoints (`/api/v1/auth/*`).

    Login/registration brute-force protection: a tight per-IP window makes
    credential stuffing slow without affecting authenticated traffic.
    """

    scope = "auth"
    path_prefixes = ("/api/v1/auth/",)


class WalletThrottle(PathScopedThrottle):
    """Limit for claim operations that touch the claim signer/ledger.

    POST mutations under `/api/v1/claims/` and the EIP-712 authorization
    GET are throttled; plain claim reads are not.
    """

    scope = "wallet"
    path_prefixes = ("/api/v1/claims/",)

    def applies_to(self, request):
        if not super().applies_to(request):
            return False
        is_mutation = request.method in {"POST", "PUT", "PATCH", "DELETE"}
        is_authorization = request.path.endswith("/authorization/")
        return is_mutation or is_authorization