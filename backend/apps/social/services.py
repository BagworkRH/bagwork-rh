"""X account linking service (Spec 03).

Flow: authorize -> callback (verify state/PKCE) -> exchange code -> identity
-> match to one platform seller -> encrypt credentials -> store -> mark
connected.
"""
import json

from apps.audit.models import AuditLog

from .crypto_utils import encrypt_secret
from .models import XAccount


def link_x_account(seller, identity, *, actor=None) -> XAccount:
    """Persist a connected X account (idempotent per provider_user_id)."""
    creds = json.dumps(
        {
            "access_token": identity.get("access_token", ""),
            "refresh_token": identity.get("refresh_token", ""),
        }
    ).encode("utf-8")
    ciphertext, iv = encrypt_secret(creds.decode("utf-8"))

    scopes = identity.get("scopes", [])

    account, created = XAccount.objects.update_or_create(
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
        action="X_ACCOUNT_LINKED",
        object_type="XAccount",
        object_id=str(account.pk),
        metadata={"provider_user_id": account.provider_user_id, "seller_code": seller.seller_code},
    )
    return account


def disconnect_x_account(seller, account, *, actor=None) -> None:
    """Disconnect (not delete) the linked X account for audit purposes."""
    account.status = "DISCONNECTED"
    account.save(update_fields=["status"])
    AuditLog.objects.create(
        actor=actor,
        action="X_ACCOUNT_DISCONNECTED",
        object_type="XAccount",
        object_id=str(account.pk),
        metadata={"seller_code": seller.seller_code},
    )