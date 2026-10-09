"""OAuth credential encryption-key rotation (Spec 05 Phase 8)."""
import os
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.social.crypto_utils import (
    decrypt_secret,
    encrypt_secret,
    key_from_material,
)
from apps.social.models import SocialAccount

from .helpers import make_user

LEGACY = "legacy-single-secret"
NEW = "dedicated-new-key"
CREDS = '{"access_token": "tok", "refresh_token": "ref"}'


def _make_account(plaintext, material, provider_user_id="1"):
    _, profile = make_user()
    ciphertext, iv = encrypt_secret(plaintext, key=key_from_material(material))
    return SocialAccount.objects.create(
        seller=profile,
        platform="x",
        provider_user_id=provider_user_id,
        username="acct",
        encrypted_credentials=ciphertext,
        credentials_iv=iv,
    )


def _decrypt_with_current(account):
    return decrypt_secret(bytes(account.encrypted_credentials), bytes(account.credentials_iv))


class RotateSocialCredentialsTests(TestCase):
    def test_re_encrypts_rows_to_the_current_key(self):
        account = _make_account(CREDS, LEGACY)

        with override_settings(SOCIAL_ENCRYPTION_KEY=NEW):
            with mock.patch.dict(os.environ, {"SOCIAL_ENCRYPTION_KEY_OLD": LEGACY}):
                call_command("rotate_social_credentials")
            account.refresh_from_db()
            # Decrypts under the NEW current key, and the plaintext is unchanged.
            self.assertEqual(_decrypt_with_current(account), CREDS)

    def test_refuses_when_the_old_and_new_keys_match(self):
        _make_account(CREDS, NEW)
        with override_settings(SOCIAL_ENCRYPTION_KEY=NEW):
            with mock.patch.dict(os.environ, {"SOCIAL_ENCRYPTION_KEY_OLD": NEW}):
                with self.assertRaises(CommandError):
                    call_command("rotate_social_credentials")

    def test_dry_run_writes_nothing(self):
        account = _make_account(CREDS, LEGACY)
        before = bytes(account.encrypted_credentials)

        with override_settings(SOCIAL_ENCRYPTION_KEY=NEW):
            with mock.patch.dict(os.environ, {"SOCIAL_ENCRYPTION_KEY_OLD": LEGACY}):
                call_command("rotate_social_credentials", dry_run=True)

        account.refresh_from_db()
        self.assertEqual(bytes(account.encrypted_credentials), before)
        # Still decryptable under the OLD key.
        self.assertEqual(
            decrypt_secret(
                bytes(account.encrypted_credentials),
                bytes(account.credentials_iv),
                key=key_from_material(LEGACY),
            ),
            CREDS,
        )

    def test_skips_rows_without_credentials(self):
        _, profile = make_user()
        SocialAccount.objects.create(
            seller=profile, platform="x", provider_user_id="2", username="nocreds"
        )
        with override_settings(SOCIAL_ENCRYPTION_KEY=NEW):
            with mock.patch.dict(os.environ, {"SOCIAL_ENCRYPTION_KEY_OLD": LEGACY}):
                call_command("rotate_social_credentials")  # must not raise

    def test_falls_back_to_secret_key_as_the_legacy_source(self):
        # The pre-rotation install has no SOCIAL_ENCRYPTION_KEY; rows are under
        # SHA-256(SECRET_KEY). Introducing a dedicated key then rotating must work.
        with override_settings(SECRET_KEY=LEGACY, SOCIAL_ENCRYPTION_KEY=""):
            account = _make_account(CREDS, LEGACY)
            with override_settings(SOCIAL_ENCRYPTION_KEY=NEW):
                with mock.patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("SOCIAL_ENCRYPTION_KEY_OLD", None)
                    call_command("rotate_social_credentials")
            account.refresh_from_db()
            # Now under the NEW key (decrypt explicitly: the override has exited).
            self.assertEqual(
                decrypt_secret(
                    bytes(account.encrypted_credentials),
                    bytes(account.credentials_iv),
                    key=key_from_material(NEW),
                ),
                CREDS,
            )
