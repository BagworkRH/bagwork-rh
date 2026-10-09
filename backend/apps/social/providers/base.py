"""Social platform provider adapter (Spec 03).

The rest of the application must never depend directly on any single platform's
API. All provider access flows through this interface so a platform can be
added, removed or degraded without touching views, services or tasks — and so
losing one platform's API access is not a business-ending event.
"""
from abc import ABC, abstractmethod


class SocialProviderError(Exception):
    """Raised for provider-level failures (network, rate limit, auth)."""


class SocialProvider(ABC):
    """Interface every social platform adapter implements.

    Implementations set `platform` to one of
    `apps.social.models.SocialPlatform`. All external identifiers returned are
    opaque strings scoped to that platform.
    """

    platform = ""

    @abstractmethod
    def authorize(self, request, scopes, *, state, code_verifier):
        """Build the OAuth authorization URL for caller-supplied PKCE material.

        `state` and `code_verifier` are generated *and persisted* by the caller
        (the connect endpoint), not by the adapter. The return leg is a top-level
        browser navigation that cannot carry the caller's bearer token, so the
        correlation handle has to live somewhere the callback can read without a
        session — and that is the caller's job, not the adapter's.
        """
        raise NotImplementedError

    @abstractmethod
    def callback(self, request, state, code, *, code_verifier=None):
        """Handle the OAuth callback; exchange code; return identity.

        The caller has already resolved `state` to a user and passes the matching
        `code_verifier`; adapters whose flow has no PKCE (e.g. TikTok) ignore it.
        """
        raise NotImplementedError

    @abstractmethod
    def get_account(self, access_token):
        """Fetch the authenticated account identity."""
        raise NotImplementedError

    @abstractmethod
    def discover_posts(self, access_token, username, campaign, since, until):
        """Discover qualifying posts for a campaign window."""
        raise NotImplementedError

    @abstractmethod
    def get_post(self, access_token, post_id):
        """Fetch a single post."""
        raise NotImplementedError

    @abstractmethod
    def get_metrics(self, access_token, post_id):
        """Fetch metrics available to the authorized account.

        Returns a dict that may contain any of: impressions, likes, reposts,
        replies, quotes, bookmarks. Platforms that do not expose a metric
        simply omit it rather than returning a fabricated zero.
        """
        raise NotImplementedError

    @abstractmethod
    def revoke(self, access_token):
        """Revoke the access token."""
        raise NotImplementedError