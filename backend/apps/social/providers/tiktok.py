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
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests

from .base import SocialProvider, SocialProviderError

AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
API_BASE = "https://open.tiktokapis.com/v2"

# Fields we request. Anything not returned is simply absent from the payload.
VIDEO_FIELDS = "id,create_time,share_url,title,view_count,like_count,comment_count,share_count"
# Discovery needs title + create_time + share_url; metrics are not needed here.
VIDEO_LIST_FIELDS = "id,create_time,share_url,title"
# Documented maximum page size for POST /v2/video/list/.
VIDEO_PAGE_SIZE = 20
# Cap pagination so a pathological account cannot loop the poller forever.
MAX_DISCOVERY_PAGES = 5

# TikTok metric name -> our canonical metric name.
METRIC_MAP = {
    "impressions": "view_count",
    "likes": "like_count",
    "replies": "comment_count",
    "reposts": "share_count",
}


def _epoch_millis(value) -> int | None:
    """Datetime -> UTC Unix milliseconds, the unit TikTok's cursor expects."""
    if value is None:
        return None
    return int(value.timestamp() * 1000)


class OfficialTikTokProvider(SocialProvider):
    """TikTok Content Posting API adapter (OAuth2 authorization code)."""

    platform = "tiktok"

    def __init__(self, user=None, client_key=None, client_secret=None, redirect_uri=None):
        self.client_key = client_key
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def _credentials(self):
        from django.conf import settings  # noqa: PLC0415

        client_key = self.client_key or getattr(settings, "TIKTOK_CLIENT_KEY", None)
        client_secret = self.client_secret or getattr(settings, "TIKTOK_CLIENT_SECRET", None)
        redirect_uri = self.redirect_uri or getattr(settings, "TIKTOK_REDIRECT_URI", None)
        if not client_key or not client_secret or not redirect_uri:
            raise SocialProviderError("TikTok API credentials are not configured.")
        return client_key, client_secret, redirect_uri

    def authorize(self, request, scopes, *, state, code_verifier=None):
        from django.urls import reverse  # noqa: PLC0415

        client_key, _, _ = self._credentials()

        # TikTok's flow has no PKCE, so `code_verifier` is ignored; `state` is
        # generated and persisted by the caller, exactly as for X.
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

    def callback(self, request, state, code, *, code_verifier=None):
        client_key, client_secret, _ = self._credentials()

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
        """Discover the creator's own uploads within a campaign window.

        Uses TikTok's `POST /v2/video/list/` (Display API), which returns the
        authenticated user's public video posts newest-first and takes the
        `video.list` scope our OAuth flow already requests. `cursor` is a UTC
        Unix timestamp in milliseconds, so it doubles as the "posts before this"
        watermark and repeated polls stay cheap.

        A TikTok video is always the creator's own upload, so it is original by
        construction -- there is no repost/quote analogue to check.
        """
        found = []
        # `cursor` is exclusive: it fetches videos posted *before* the given
        # timestamp, so the first page passes nothing and later pages use `until`.
        cursor = _epoch_millis(until) if until else None
        for _ in range(MAX_DISCOVERY_PAGES):
            body = self._list_videos(access_token, cursor)
            data = body.get("data") or {}
            for video in data.get("videos") or []:
                payload = self.normalize_video(video)
                created = payload.get("created_at")
                if since and created and created < since:
                    # Videos arrive newest-first, so the rest are older too.
                    return found
                found.append(payload)
            if not data.get("has_more"):
                break
            cursor = data.get("cursor")
            if not cursor:
                break
        return found

    def _list_videos(self, access_token, cursor=None):
        body = {"max_count": VIDEO_PAGE_SIZE}  # documented maximum is 20
        if cursor:
            body["cursor"] = cursor
        resp = requests.post(
            f"{API_BASE}/video/list/",
            headers=self._headers(access_token),
            params={"fields": VIDEO_LIST_FIELDS},
            json=body,
            timeout=30,
        )
        if not resp.ok:
            raise SocialProviderError(f"Video list failed: HTTP {resp.status_code}")
        payload = resp.json()
        error = payload.get("error") or {}
        if error.get("code") not in ("ok", "", None):
            raise SocialProviderError(f"Video list error: {error.get('code')}")
        return payload

    @staticmethod
    def normalize_video(video) -> dict:
        """Map a TikTok video object into our provider payload shape.

        `create_time` is Unix seconds; `share_url` is the canonical link. A
        TikTok video is the creator's own upload, so originality holds by
        construction rather than by inference.
        """
        created = video.get("create_time")
        created_at = (
            datetime.fromtimestamp(int(created), tz=timezone.utc) if created else None
        )
        video_id = str(video.get("id", ""))
        return {
            "post_id": video_id,
            "text": video.get("title") or video.get("video_description") or "",
            "created_at": created_at,
            "post_url": video.get("share_url") or f"https://www.tiktok.com/@i/video/{video_id}",
            "is_repost": False,
            "is_quote": False,
        }

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

