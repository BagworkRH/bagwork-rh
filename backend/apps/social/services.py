"""Social account linking service (Spec 03).

Flow: authorize -> callback (verify state/PKCE) -> exchange code -> identity
-> match to one platform seller -> encrypt credentials -> store -> mark
connected.

Identities are keyed by `(platform, provider_user_id)`: ids are only unique
within their own platform, so a seller can hold the same numeric id on X and
TikTok without one overwriting the other.
"""
import json

from apps.audit.models import AuditLog

from .crypto_utils import encrypt_secret
from .models import SocialAccount, SocialPlatform


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
            "token_expiry": None,
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