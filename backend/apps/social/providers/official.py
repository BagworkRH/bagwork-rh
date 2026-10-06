"""Official X API provider adapter.

Implements the SocialProvider interface using the official X (Twitter) OAuth2
with PKCE flow. Credentials always come from environment variables
(X_CLIENT_ID, X_CLIENT_SECRET, X_REDIRECT_URI). Never hard-code credentials.
"""
import base64
import hashlib
import secrets
from datetime import timezone as dt_timezone
from urllib.parse import urlencode

import requests
from django.utils import timezone

from .base import SocialProvider, SocialProviderError

# Session keys are namespaced by platform so an X callback can never consume a
# different platform's PKCE verifier or OAuth state.
SESSION_PREFIX = "social_oauth"

# X's `referenced_tweets[].type` values, confirmed against the live API.
# `retweeted` is the one that matters: the original code tested for "reposted",
# which X never returns, so every real retweet was recorded as an original and
# was therefore payable.
KNOWN_REFERENCE_TYPES = frozenset({"retweeted", "quoted", "replied_to"})


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _rfc3339(value) -> str:
    """Format a datetime as RFC 3339 with at most millisecond precision.

    X rejects a bare date, so the offset is always included explicitly — and,
    found against the live API, it also rejects *microsecond* precision. Its
    own error message gives the accepted pattern as
    `yyyy-MM-dd'T'HH:mm:ss[.SSS]X`, i.e. seconds plus at most milliseconds.
    Django's `timezone.now()` carries microseconds, so without this truncation
    the first real discovery call fails with HTTP 400.
    """
    if value is None:
        return ""
    if value.tzinfo is None:
        value = timezone.make_aware(value, dt_timezone.utc)
    value = value.astimezone(dt_timezone.utc).replace(microsecond=(value.microsecond // 1000) * 1000)
    text = value.isoformat().replace("+00:00", "Z")
    # `isoformat` always prints six fractional digits; X's pattern allows at
    # most three, so drop the trailing zeros: .558000 -> .558, .000 -> (none).
    if "." in text:
        head, tail = text.split(".", 1)
        digits, suffix = tail[:-1], tail[-1:]  # keep the trailing Z aside
        digits = digits.rstrip("0")
        text = f"{head}.{digits}{suffix}" if digits else f"{head}{suffix}"
    return text


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
            "https://api.twitter.com/2/tweets/"
            f"{post_id}?tweet.fields=created_at,public_metrics,text,referenced_tweets",
            headers=self._headers(access_token),
            timeout=30,
        )
        if not resp.ok:
            raise SocialProviderError(f"Post fetch failed: HTTP {resp.status_code}")
        return resp.json()["data"]

    @staticmethod
    def normalize_post(raw) -> dict:
        """Map an X API tweet into our provider payload shape.

        `referenced_tweets` is how X marks a repost or a quote; without it we
        cannot tell a creator's own post from amplification of someone else's,
        which is the difference between earning a reward and not.

        The type strings are X's, verified against the live API rather than
        taken from documentation: it returns `retweeted`, not `reposted`. That
        distinction cost real money in principle — a retweet whose type we
        failed to recognise was recorded as an original, provider-confirmed
        post and therefore payable. The fixtures had encoded the same guess, so
        the suite stayed green while the gate was open.
        """
        refs = raw.get("referenced_tweets") or []
        ref_types = {ref.get("type") for ref in refs}
        created_at = raw.get("created_at")
        if created_at:
            # X returns ISO-8601 with a trailing Z; make it explicit.
            created_at = created_at.replace("Z", "+00:00")

        # X's documented enum is retweeted | quoted | replied_to. A reply is
        # the creator's own words, so it is not amplification; anything else
        # means the post is not wholly the creator's, and an unrecognised type
        # must fail closed rather than be assumed original.
        unrecognised = ref_types - KNOWN_REFERENCE_TYPES
        is_repost = "retweeted" in ref_types or bool(unrecognised)
        return {
            "post_id": str(raw.get("id", "")),
            "text": raw.get("text", ""),
            "created_at": created_at,
            "post_url": f"https://x.com/i/status/{raw.get('id', '')}",
            "is_repost": is_repost,
            "is_quote": "quoted" in ref_types,
        }

    def _get_timeline(self, access_token, user_id, params):
        """One page of the timeline.

        A connected OAuth2 *user* token is required: the endpoint's security is
        `[OAuth2UserToken: [tweet.read, users.read]]`. An app-only bearer cannot
        read a user's timeline.
        """
        resp = requests.get(
            f"https://api.x.com/2/users/{user_id}/timelines/reverse_chronological",
            headers=self._headers(access_token),
            params=params,
            timeout=30,
        )
        if not resp.ok:
            raise SocialProviderError(f"Timeline fetch failed: HTTP {resp.status_code}")
        return resp.json()

    def discover_posts(self, access_token, username, campaign, since, until):
        """Discover the user's own posts within a campaign window.

        X renamed this endpoint; it is now
        `GET /2/users/:id/timelines/reverse_chronological` (API v2.168), not
        `/2/users/:id/tweets`. It requires an OAuth 2.0 *user* token with
        `tweet.read` + `users.read`; an app-only bearer cannot read a timeline.

        `exclude=retweets,replies` keeps the result to the creator's own
        original posts, which is exactly what this platform pays for. We still
        read `referenced_tweets` rather than trusting that filter, because the
        filter is an optimisation and originality is the thing we get paid on.

        `since` is the high-water mark (last successful poll) so repeated calls
        stay cheap and idempotent; the campaign window bounds the first call.
        """
        user_id = self._resolve_user_id(access_token, username)
        start = since or campaign.start_at
        params = {
            "max_results": 100,  # documented maximum
            "start_time": _rfc3339(start),
            "end_time": _rfc3339(until or campaign.end_at),
            "exclude": "retweets,replies",
            "tweet.fields": (
                "created_at,public_metrics,text,referenced_tweets,conversation_id"
            ),
        }
        body = self._get_timeline(access_token, user_id, params)
        return [self.normalize_post(tweet) for tweet in body.get("data") or []]

    def _resolve_user_id(self, access_token, username=None):
        """Resolve the numeric user id the timeline endpoint requires."""
        if username and str(username).isdigit():
            return str(username)
        account = self.get_account(access_token)
        return str(account["provider_user_id"])

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