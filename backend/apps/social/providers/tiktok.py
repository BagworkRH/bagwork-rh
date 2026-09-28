"""Official TikTok provider adapter.

Implements the SocialProvider interface against TikTok's Content Posting API
(OAuth 2.0 authorization code flow). Credentials come from the environment
(TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET); never hard-code them.

Scope is deliberately limited to what a rewards platform needs: identify the
creator's own account, and read the creator's own videos' public statistics.
This adapter never posts on a creator's behalf — creators publish their own
content, which keeps the platform on the right side of every social network's
automation policy.

Metrics are reported only when TikTok actually exposes them; a metric that is
not available is omitted rather than reported as a fabricated zero.
"""
import secrets
from urllib.parse import urlencode

import requests

from .base import SocialProvider, SocialProviderError

# Session keys are namespaced by platform, matching the X adapter.
SESSION_PREFIX = "social_oauth"

AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
API_BASE = "https://open.tiktokapis.com/v2"

# Fields we request. Anything not returned is simply absent from the payload.
VIDEO_FIELDS = "id,create_time,share_url,title,view_count,like_count,comment_count,share_count"

# TikTok metric name -> our canonical metric name.
METRIC_MAP = {
    "impressions": "view_count",
    "likes": "like_count",
    "replies": "comment_count",
    "reposts": "share_count",
}


class OfficialTikTokProvider(SocialProvider):
    """TikTok Content Posting API adapter (OAuth2 authorization code)."""

    platform = "tiktok"

    def __init__(self, user=None, client_key=None, client_secret=None, redirect_uri=None):
        self.client_key = client_key
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def _session_key(self, suffix: str) -> str:
        return f"{SESSION_PREFIX}:{self.platform}:{suffix}"

    def _credentials(self):
        from django.conf import settings  # noqa: PLC0415

        client_key = self.client_key or getattr(settings, "TIKTOK_CLIENT_KEY", None)
        client_secret = self.client_secret or getattr(settings, "TIKTOK_CLIENT_SECRET", None)
        redirect_uri = self.redirect_uri or getattr(settings, "TIKTOK_REDIRECT_URI", None)
        if not client_key or not client_secret or not redirect_uri:
            raise SocialProviderError("TikTok API credentials are not configured.")
        return client_key, client_secret, redirect_uri

    def authorize(self, request, scopes):
        from django.urls import reverse  # noqa: PLC0415

        client_key, _, _ = self._credentials()

        state = secrets.token_urlsafe(32)
        # TikTok's OAuth flow has no PKCE, but the state still round-trips and
        # is namespaced so a TikTok callback cannot consume an X session.
        request.session[self._session_key("state")] = state
        request.session[self._session_key("scopes")] = scopes

        callback_url = request.build_absolute_uri(
            reverse("social:callback", kwargs={"platform": self.platform})
        )
        params = {
            "client_key": client_key,
            "redirect_uri": callback_url,
            "response_type": "code",
            "scope": " ".join(scopes),
            "state": state,
        }
        return AUTHORIZE_URL + "?" + urlencode(params)

    def callback(self, request, state, code):
        client_key, client_secret, _ = self._credentials()
        session_state = request.session.get(self._session_key("state"))
        if not session_state or session_state != state:
            raise SocialProviderError("OAuth state mismatch.")

        from django.urls import reverse  # noqa: PLC0415

        callback_url = request.build_absolute_uri(
            reverse("social:callback", kwargs={"platform": self.platform})
        )
        token_resp = requests.post(
            TOKEN_URL,
            data={
                "client_key": client_key,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": callback_url,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        if not token_resp.ok:
            raise SocialProviderError(f"Token exchange failed: HTTP {token_resp.status_code}")
        tokens = token_resp.json()
        if tokens.get("error"):
            raise SocialProviderError(f"Token exchange error: {tokens['error']}")

        account = self.get_account(tokens["access_token"])
        account["access_token"] = tokens["access_token"]
        account["refresh_token"] = tokens.get("refresh_token", "")
        return account

    def _headers(self, access_token):
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }

    def get_account(self, access_token):
        resp = requests.post(
            f"{API_BASE}/user/info/",
            headers=self._headers(access_token),
            json={
                "fields": ["open_id", "union_id", "display_name", "username", "avatar_url"]
            },
            timeout=30,
        )
        if not resp.ok:
            raise SocialProviderError(f"Account fetch failed: HTTP {resp.status_code}")
        body = resp.json()
        if body.get("error"):
            raise SocialProviderError(f"Account fetch error: {body['error']}")
        user = body.get("data", {}).get("user", {})
        return {
            "provider_user_id": user.get("open_id", ""),
            "username": user.get("username") or user.get("display_name", ""),
            "display_name": user.get("display_name", ""),
            "avatar_url": user.get("avatar_url", ""),
            "scopes": [],
        }

    def get_post(self, access_token, post_id):
        resp = requests.post(
            f"{API_BASE}/video/query/",
            headers=self._headers(access_token),
            json={"filters": {"video_ids": [post_id]}, "fields": [VIDEO_FIELDS]},
            timeout=30,
        )
        if not resp.ok:
            raise SocialProviderError(f"Post fetch failed: HTTP {resp.status_code}")
        body = resp.json()
        if body.get("error"):
            raise SocialProviderError(f"Post fetch error: {body['error']}")
        videos = body.get("data", {}).get("videos", [])
        return videos[0] if videos else {}

    def discover_posts(self, access_token, username, campaign, since, until):
        # The public Content Posting API exposes no user-post search endpoint;
        # discovering posts is out of scope for this adapter.
        raise SocialProviderError(
            "TikTok post discovery is not available through this adapter."
        )

    def get_metrics(self, access_token, post_id):
        video = self.get_post(access_token, post_id)
        if not video:
            return {}
        # Only report a metric TikTok actually returned, so an absent field
        # is never mistaken for a genuine zero.
        return {
            field: int(video[key])
            for field, key in METRIC_MAP.items()
            if video.get(key) is not None
        }

    def revoke(self, access_token):
        client_key, _, _ = self._credentials()
        resp = requests.post(
            f"{API_BASE}/oauth/revoke/",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={"client_key": client_key, "token": access_token},
            timeout=30,
        )
        return resp.ok

