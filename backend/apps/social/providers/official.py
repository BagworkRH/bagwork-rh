"""Official X API provider adapter.

Implements the SocialProvider interface using the official X (Twitter) OAuth2
with PKCE flow. Credentials always come from environment variables
(X_CLIENT_ID, X_CLIENT_SECRET, X_REDIRECT_URI). Never hard-code credentials.
"""
import base64
import hashlib
import secrets
from urllib.parse import urlencode

import requests

from .base import SocialProvider, SocialProviderError

# Session keys are namespaced by platform so an X callback can never consume a
# different platform's PKCE verifier or OAuth state.
SESSION_PREFIX = "social_oauth"


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class OfficialXProvider(SocialProvider):
    """Official X API (OAuth2 + PKCE) adapter."""

    platform = "x"

    def __init__(self, user=None, client_id=None, client_secret=None, redirect_uri=None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def _session_key(self, suffix: str) -> str:
        return f"{SESSION_PREFIX}:{self.platform}:{suffix}"

    def _credentials(self):
        from django.conf import settings  # noqa: PLC0415

        client_id = self.client_id or getattr(settings, "X_CLIENT_ID", None)
        client_secret = self.client_secret or getattr(settings, "X_CLIENT_SECRET", None)
        redirect_uri = self.redirect_uri or getattr(settings, "X_REDIRECT_URI", None)
        if not client_id or not client_secret or not redirect_uri:
            raise SocialProviderError("X API credentials are not configured.")
        return client_id, client_secret, redirect_uri

    def authorize(self, request, scopes):
        from django.urls import reverse  # noqa: PLC0415

        client_id, _, _ = self._credentials()

        state = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(48)
        challenge = _pkce_challenge(code_verifier)

        # Store the verifier + state on the session for the callback step.
        request.session[self._session_key("state")] = state
        request.session[self._session_key("verifier")] = code_verifier
        request.session[self._session_key("scopes")] = scopes

        callback_url = request.build_absolute_uri(
            reverse("social:callback", kwargs={"platform": self.platform})
        )
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": callback_url,
            "scope": " ".join(scopes),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return "https://twitter.com/i/oauth2/authorize?" + urlencode(params)

    def callback(self, request, state, code):
        client_id, client_secret, _ = self._credentials()
        session_state = request.session.get(self._session_key("state"))
        if not session_state or session_state != state:
            raise SocialProviderError("OAuth state mismatch.")

        code_verifier = request.session.get(self._session_key("verifier"))
        if not code_verifier:
            raise SocialProviderError("Missing PKCE verifier.")

        from django.urls import reverse  # noqa: PLC0415

        callback_url = request.build_absolute_uri(
            reverse("social:callback", kwargs={"platform": self.platform})
        )
        token_resp = requests.post(
            "https://api.twitter.com/2/oauth2/token",
            data={
                "code": code,
                "grant_type": "authorization_code",
                "client_id": client_id,
                "redirect_uri": callback_url,
                "code_verifier": code_verifier,
            },
            auth=(client_id, client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        if not token_resp.ok:
            raise SocialProviderError(f"Token exchange failed: HTTP {token_resp.status_code}")
        tokens = token_resp.json()

        account = self.get_account(tokens["access_token"])
        account["access_token"] = tokens["access_token"]
        account["refresh_token"] = tokens.get("refresh_token", "")
        return account

    def _headers(self, access_token):
        return {"Authorization": f"Bearer {access_token}"}

    def get_account(self, access_token):
        resp = requests.get(
            "https://api.twitter.com/2/users/me?user.fields=name,username,profile_image_url",
            headers=self._headers(access_token),
            timeout=30,
        )
        if not resp.ok:
            raise SocialProviderError(f"Account fetch failed: HTTP {resp.status_code}")
        data = resp.json()["data"]
        return {
            "provider_user_id": data["id"],
            "username": data["username"],
            "display_name": data.get("name", ""),
            "avatar_url": data.get("profile_image_url", ""),
            "scopes": [],
        }

    def get_post(self, access_token, post_id):
        resp = requests.get(
            f"https://api.twitter.com/2/tweets/{post_id}?tweet.fields=created_at,public_metrics,text",
            headers=self._headers(access_token),
            timeout=30,
        )
        if not resp.ok:
            raise SocialProviderError(f"Post fetch failed: HTTP {resp.status_code}")
        return resp.json()["data"]

    def discover_posts(self, access_token, username, campaign, since, until):
        # Only lookup endpoints within the authorized grant may be used.
        raise SocialProviderError("Post discovery requires a grant that this app does not have.")

    def get_metrics(self, access_token, post_id):
        post = self.get_post(access_token, post_id)
        pub = post.get("public_metrics", {})
        return {
            "impressions": int(pub.get("impression_count", 0)),
            "likes": int(pub.get("like_count", 0)),
            "reposts": int(pub.get("retweet_count", 0)),
            "replies": int(pub.get("reply_count", 0)),
            "quotes": int(pub.get("quote_count", 0)),
            "bookmarks": int(pub.get("bookmark_count", 0)),
        }

    def revoke(self, access_token):
        client_id, _, _ = self._credentials()
        resp = requests.post(
            "https://api.twitter.com/2/oauth2/revoke",
            data={"token": access_token, "client_id": client_id},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        return resp.ok