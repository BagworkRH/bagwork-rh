"""X provider adapter (Spec 03).

The rest of the application must never depend directly on raw X API calls.
All provider access flows through this adapter so provider limitations can be
handled gracefully.
"""
from abc import ABC, abstractmethod


class XProviderError(Exception):
    """Raised for provider-level failures (network, rate limit, auth)."""


class XProvider(ABC):
    """Interface for the X API provider."""

    name = "x"

    @abstractmethod
    def authorize(self, request, scopes):
        """Build the OAuth authorization URL."""
        raise NotImplementedError

    @abstractmethod
    def callback(self, request, state, code):
        """Handle the OAuth callback; exchange code; return identity."""
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
        """Fetch metrics available to the authorized account."""
        raise NotImplementedError

    @abstractmethod
    def revoke(self, access_token):
        """Revoke the access token."""
        raise NotImplementedError