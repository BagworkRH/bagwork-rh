"""Development placeholder provider.

MARKED AS DEVELOPMENT MOCK (per Spec 05: clearly mark development mocks).
This is NOT wired into production configuration. It exists so the X link
flow can be developed and tested without live credentials.
"""
from django.utils import timezone

from .base import XProvider


class MockXProvider(XProvider):
    """DEVELOPMENT MOCK — do not enable in production."""

    name = "mock-x"
    is_mock = True

    def __init__(self, user):
        self._user = user

    def authorize(self, request, scopes):
        from django.urls import reverse  # noqa: PLC0415

        return request.build_absolute_uri(
            reverse("social:x-callback") + "?state=mock-state&code=mock-code"
        )

    def callback(self, request, state, code):
        return {
            "provider_user_id": f"mock-{self._user.id}",
            "username": self._user.username or "mockuser",
            "display_name": self._user.username or "Mock User",
            "avatar_url": "",
            "scopes": ["tweet.read", "users.read"],
        }

    def get_account(self, access_token):
        return {
            "provider_user_id": f"mock-{self._user.id}",
            "username": self._user.username or "mockuser",
            "display_name": self._user.username or "Mock User",
        }

    def get_post(self, access_token, post_id):
        return {
            "post_id": post_id,
            "text": "Mock post for development",
            "created_at": timezone.now().isoformat(),
        }

    def discover_posts(self, access_token, username, campaign, since, until):
        return []

    def get_metrics(self, access_token, post_id):
        return {
            "impressions": 0,
            "likes": 0,
            "reposts": 0,
            "replies": 0,
            "quotes": 0,
            "bookmarks": 0,
        }

    def revoke(self, access_token):
        return True