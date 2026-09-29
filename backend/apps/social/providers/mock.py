"""Development placeholder provider.

MARKED AS DEVELOPMENT MOCK (per Spec 05: clearly mark development mocks).
This is NOT wired into production configuration. It exists so the social link
flow can be developed and tested without live credentials for any platform.
"""
from datetime import datetime as django_datetime

from django.utils import timezone

from .base import SocialProvider


class MockSocialProvider(SocialProvider):
    """DEVELOPMENT MOCK — do not enable in production.

    The mock emulates whatever platform it is asked for, so multi-platform
    flows can be exercised locally without credentials.
    """

    is_mock = True

    def __init__(self, user, platform="x", discovered_posts=None):
        self._user = user
        self.platform = platform
        # Discovery is exercised in tests, so the mock needs something to
        # return. Defaults to empty, which is the honest "nothing new".
        self._discovered = list(discovered_posts or [])

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
        """Return posts that fall inside the requested window.

        Honors `since`/`until` so idempotency is testable, and marks originality
        the same way a real adapter would, so the discovery path is exercised
        end to end rather than short-circuiting at the mock.
        """
        found = []
        for raw in self._discovered:
            created = raw.get("created_at")
            if isinstance(created, str):
                created = django_datetime.fromisoformat(created)
            if since and created and created < since:
                continue
            if until and created and created > until:
                continue
            found.append(
                {
                    "post_id": str(raw["post_id"]),
                    "text": raw.get("text", ""),
                    "created_at": created,
                    "post_url": raw.get("post_url", ""),
                    "is_repost": raw.get("is_repost", False),
                    "is_quote": raw.get("is_quote", False),
                }
            )
        return found

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