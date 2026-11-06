"""Social account linking service (Spec 03).

Flow: authorize -> callback (verify state/PKCE) -> exchange code -> identity
-> match to one platform seller -> encrypt credentials -> store -> mark
connected.

Identities are keyed by `(platform, provider_user_id)`: ids are only unique
within their own platform, so a seller can hold the same numeric id on two
networks without one overwriting the other.
"""
import json
from datetime import timedelta

from cryptography.exceptions import InvalidTag
from django.conf import settings
from django.utils import timezone

from apps.audit.models import AuditLog

from .crypto_utils import decrypt_secret, encrypt_secret
from .models import SocialAccount, SocialPlatform, normalize_verified_type
from .providers import get_provider
from .providers.base import SocialProviderAuthError, SocialProviderError


def link_social_account(seller, identity, *, platform=SocialPlatform.X, actor=None) -> SocialAccount:
    """Persist a connected account (idempotent per platform + provider_user_id)."""
    creds = json.dumps(
        {
            "access_token": identity.get("access_token", ""),
            "refresh_token": identity.get("refresh_token", ""),
        }
    ).encode("utf-8")
    ciphertext, iv = encrypt_secret(creds.decode("utf-8"))

    scopes = identity.get("scopes", [])
    verified_type = normalize_verified_type(identity.get("verified_type"))

    account, created = SocialAccount.objects.update_or_create(
        platform=platform,
        provider_user_id=identity["provider_user_id"],
        defaults={
            "seller": seller,
            "username": identity["username"],
            "display_name": identity.get("display_name", ""),
            "avatar_url": identity.get("avatar_url", ""),
            "encrypted_credentials": ciphertext,
            "credentials_iv": iv,
            "scopes": scopes,
            # Recorded so a renewal can happen before the token expires,
            # not after the first 401 of a discovery run.
            "token_expiry": identity.get("expires_at"),
            # The badge was read from the provider seconds ago, so record when.
            # Discovery re-reads it on a timer because Premium lapses.
            "verified_type": verified_type,
            "verification_checked_at": timezone.now(),
            "status": "CONNECTED",
        },
    )

    AuditLog.objects.create(
        actor=actor,
        action="SOCIAL_ACCOUNT_LINKED",
        object_type="SocialAccount",
        object_id=str(account.pk),
        metadata={
            "platform": platform,
            "provider_user_id": account.provider_user_id,
            "seller_code": seller.seller_code,
            "verified_type": verified_type,
        },
    )
    return account


def disconnect_social_account(seller, account, *, actor=None) -> None:
    """Disconnect (not delete) a linked account for audit purposes."""
    account.status = "DISCONNECTED"
    account.save(update_fields=["status"])
    AuditLog.objects.create(
        actor=actor,
        action="SOCIAL_ACCOUNT_DISCONNECTED",
        object_type="SocialAccount",
        object_id=str(account.pk),
        metadata={"platform": account.platform, "seller_code": seller.seller_code},
    )

# ---------------------------------------------------------------------------
# Token renewal
# ---------------------------------------------------------------------------

# Renew this far ahead of expiry. X access tokens last ~2 hours, so a five
# minute margin costs one extra refresh per account per two hours and removes
# the race where a token expires between the check and the call.
REFRESH_MARGIN = timedelta(minutes=5)

# Set on an account whose refresh token was rejected. Nothing but its owner
# reconnecting can fix that, so polling stops instead of spending a request per
# tick on a token that will never work again.
STATUS_REAUTH_REQUIRED = "REAUTH_REQUIRED"


def load_credentials(account) -> dict:
    """Decrypt an account's stored OAuth credentials.

    Returns `{}` when the blob cannot be read — a changed
    `SOCIAL_ENCRYPTION_KEY` with no `rotate_social_credentials` run, or a
    corrupt row. The tokens are gone either way, so reporting "no credentials"
    lets the caller treat the account as needing reconnection rather than
    failing an entire discovery run on a decryption error.
    """
    if not account.encrypted_credentials:
        return {}
    try:
        return json.loads(
            decrypt_secret(bytes(account.encrypted_credentials), bytes(account.credentials_iv))
        )
    except (InvalidTag, ValueError):
        return {}


def store_credentials(account, *, access_token, refresh_token=None, expires_at=None) -> None:
    """Persist credentials for an account, re-encrypted at rest.

    `refresh_token=None` keeps the stored one: X does not always return a new
    refresh token, and writing an empty string over a live one would strand the
    account at its next expiry with no way back except a manual reconnect.
    """
    existing = load_credentials(account)
    payload = json.dumps(
        {
            "access_token": access_token,
            "refresh_token": refresh_token or existing.get("refresh_token", ""),
        }
    )
    ciphertext, iv = encrypt_secret(payload)
    account.encrypted_credentials = ciphertext
    account.credentials_iv = iv
    account.token_expiry = expires_at
    account.save(update_fields=["encrypted_credentials", "credentials_iv", "token_expiry"])


def token_needs_refresh(account) -> bool:
    """True when the stored access token is expired or about to expire."""
    expiry = account.token_expiry
    return bool(expiry and expiry <= timezone.now() + REFRESH_MARGIN)


def refresh_account_credentials(account, *, actor=None) -> str:
    """Renew an account's access token in place; returns the new token.

    Raises `SocialProviderAuthError` when the account cannot be renewed: no
    refresh token was ever granted (a connection made before `offline.access`
    was requested) or X rejected the one we hold. The account is then marked
    `REAUTH_REQUIRED` with an audit row recording why — the seller has to
    reconnect, and silently retrying would hide that from everyone.
    """
    creds = load_credentials(account)
    provider = get_provider(account.platform)
    renew = getattr(provider, "refresh_access_token", None)
    if renew is None:
        # The development mock has no token endpoint. That is not a broken
        # account, so it must not be flagged as one.
        raise SocialProviderError(f"Provider {account.platform!r} cannot refresh tokens.")

    try:
        refreshed = renew(creds.get("refresh_token", ""))
    except SocialProviderAuthError:
        _mark_reauth_required(account)
        raise

    store_credentials(
        account,
        access_token=refreshed["access_token"],
        refresh_token=refreshed.get("refresh_token"),
        expires_at=refreshed.get("expires_at"),
    )
    if account.status != "CONNECTED":
        # A renewal that worked means the account is usable again.
        account.status = "CONNECTED"
        account.save(update_fields=["status"])
    AuditLog.objects.create(
        actor=actor,
        action="SOCIAL_TOKEN_REFRESHED",
        object_type="SocialAccount",
        object_id=str(account.pk),
        metadata={"platform": account.platform, "provider_user_id": account.provider_user_id},
    )
    return refreshed["access_token"]


def with_fresh_token(account, call, *args, **kwargs):
    """Run `call(access_token, ...)`, renewing the token if that is what it needs.

    Two ways in: proactively, when the recorded expiry is within
    `REFRESH_MARGIN`; and reactively, when the provider answers 401. The
    reactive retry happens exactly once — a second 401 means the refresh token
    is gone too, which `refresh_account_credentials` will already have reported.

    Retrying is safe here because every caller is a read (`discover_posts`,
    `get_metrics`, `get_post`). This is not a general "retry anything" helper.
    """
    token = load_credentials(account).get("access_token", "")
    if token_needs_refresh(account):
        token = refresh_account_credentials(account)
    try:
        return call(token, *args, **kwargs)
    except SocialProviderAuthError:
        token = refresh_account_credentials(account)
        return call(token, *args, **kwargs)


def _mark_reauth_required(account) -> None:
    """Stop polling an account whose token can no longer be renewed."""
    account.status = STATUS_REAUTH_REQUIRED
    account.save(update_fields=["status"])
    AuditLog.objects.create(
        actor=None,
        action="SOCIAL_ACCOUNT_REAUTH_REQUIRED",
        object_type="SocialAccount",
        object_id=str(account.pk),
        metadata={"platform": account.platform, "reason": "refresh token rejected"},
    )


# ---------------------------------------------------------------------------
# Account verification
# ---------------------------------------------------------------------------

# How long a verification badge is trusted before it is re-read from the
# provider.
#
# X Premium is a *subscription*. An account can be verified when it is connected
# and unverified a month later with nothing on this side changing, so a
# connect-time check alone would let someone subscribe for one month, connect,
# cancel, and keep earning for as long as they liked. Re-reading once a day
# bounds both the damage (a lapsed badge stops earning within a day) and the
# cost (one extra API call per account per day, rather than one per poll).
VERIFICATION_TTL = timedelta(hours=24)


def verified_accounts_required() -> bool:
    """Whether posts are only tracked for accounts that carry a verification badge.

    A setting rather than a constant, because it is a product decision with a
    real cost: the X badge is a paid subscription, so requiring it excludes
    every creator who will not pay for one. That has to be flippable without a
    code change.
    """
    return bool(getattr(settings, "REQUIRE_VERIFIED_ACCOUNTS", True))


def verification_is_stale(account) -> bool:
    """True when the stored badge is old enough to be worth re-reading."""
    checked = account.verification_checked_at
    if checked is None:
        return True
    return checked <= timezone.now() - VERIFICATION_TTL


def refresh_account_verification(account, *, force=False) -> bool:
    """Re-read an account's verification badge; return whether it counts as verified.

    Within `VERIFICATION_TTL` this answers from the stored value and makes no
    call, so calling it before every poll is cheap.

    On a provider failure nothing is written: an outage must not silently strip
    a verified creator of their badge and stop their earnings, which is the same
    rule that stops a post being marked VERIFIED while the provider is down. The
    error is raised instead, so the caller can tell "no badge" from "we could not
    find out" and skip this poll rather than act on a guess.
    """
    if not force and not verification_is_stale(account):
        return account.is_verified

    provider = get_provider(account.platform)
    identity = with_fresh_token(account, provider.get_account)
    verified_type = normalize_verified_type(identity.get("verified_type"))

    changed = verified_type != account.verified_type
    account.verified_type = verified_type
    account.verification_checked_at = timezone.now()
    account.save(update_fields=["verified_type", "verification_checked_at"])

    if changed:
        # A badge appearing or disappearing changes whether this creator can be
        # paid, so it is an auditable event rather than a quiet field update.
        AuditLog.objects.create(
            actor=None,
            action="SOCIAL_VERIFICATION_CHANGED",
            object_type="SocialAccount",
            object_id=str(account.pk),
            metadata={
                "platform": account.platform,
                "provider_user_id": account.provider_user_id,
                "seller_code": account.seller.seller_code,
                "verified_type": verified_type,
            },
        )
    return account.is_verified

