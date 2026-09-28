"""Development placeholder provider.

MARKED AS DEVELOPMENT MOCK (per Spec 05: clearly mark development mocks).
This is NOT wired into production configuration. It exists so the social link
flow can be developed and tested without live credentials for any platform.
"""
from django.utils import timezone

from .base import SocialProvider


class MockSocialProvider(SocialProvider):
    """DEVELOPMENT MOCK — do not enable in production.

    The mock emulates whatever platform it is asked for, so multi-platform
    flows can be exercised locally without credentials.
    """

    is_mock = True

    def __init__(self, user, platform="x"):
        self._user = user
        self.platform = platform

    def _suffix(self):
        # Distinct per platform so mock ids do not collide across platforms.
        return self.platform

    def authorize(self, request, scopes):
        from django.urls import reverse  # noqa: PLC0415

        return request.build_absolute_uri(
            reverse("social:callback", kwargs={"platform": self.platform})
            + "?state=mock-state&code=mock-code"
        )

    def callback(self, request, state, code):
        return {
            "provider_user_id": f"mock-{self._suffix()}-{self._user.id}",
            "username": self._user.username or "mockuser",
            "display_name": self._user.username or "Mock User",
            "avatar_url": "",
            "scopes": ["read", "user_info"],
        }

    def get_account(self, access_token):
        return {
            "provider_user_id": f"mock-{self._suffix()}-{self._user.id}",
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