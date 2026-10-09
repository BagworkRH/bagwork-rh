"""Re-encrypt stored OAuth credentials under the current encryption key.

Rotating the key that encrypts stored OAuth tokens is two steps: change the
secret, then re-encrypt every row from the old material to the new one. This
does the second step, and is the counterpart to `SOCIAL_ENCRYPTION_KEY`.

The old material is read from an environment variable (default
`SOCIAL_ENCRYPTION_KEY_OLD`), falling back to `SECRET_KEY` — the legacy source,
for the case where a dedicated `SOCIAL_ENCRYPTION_KEY` has just been introduced
and existing rows are still under the SECRET_KEY-derived key. Secrets are not
passed as command-line arguments: argv is visible in `ps` and shell history.

    SOCIAL_ENCRYPTION_KEY=<new> SOCIAL_ENCRYPTION_KEY_OLD=<old> \\
        python manage.py rotate_social_credentials
"""
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.social.crypto_utils import current_key, decrypt_secret, encrypt_secret, key_from_material
from apps.social.models import SocialAccount


class Command(BaseCommand):
    help = "Re-encrypt stored OAuth credentials from the old key to the current key."

    def add_arguments(self, parser):
        parser.add_argument(
            "--old-env",
            default="SOCIAL_ENCRYPTION_KEY_OLD",
            help="Environment variable holding the OLD key material (default: SECRET_KEY).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing.",
        )

    def handle(self, *args, **options):
        old_material = os.environ.get(options["old_env"], "").strip() or settings.SECRET_KEY
        old_key = key_from_material(old_material)
        new_key = current_key()

        if old_key == new_key:
            raise CommandError(
                "The old and current keys are identical. Set SOCIAL_ENCRYPTION_KEY to the "
                f"new material and pass the previous material via {options['old_env']}. "
                "Nothing to rotate."
            )

        rotated = skipped = failed = 0
        for account in SocialAccount.objects.all().iterator():
            raw = account.encrypted_credentials
            iv_raw = account.credentials_iv
            if not raw or not iv_raw:
                skipped += 1
                continue
            try:
                plaintext = decrypt_secret(bytes(raw), bytes(iv_raw), key=old_key)
            except Exception:
                failed += 1
                self.stderr.write(
                    self.style.WARNING(
                        f"account {account.pk}: credentials are not decryptable with the old key "
                        "(already rotated?)"
                    )
                )
                continue

            if options["dry_run"]:
                rotated += 1
                continue

            new_ciphertext, new_iv = encrypt_secret(plaintext, key=new_key)
            account.encrypted_credentials = new_ciphertext
            account.credentials_iv = new_iv
            account.save(update_fields=["encrypted_credentials", "credentials_iv"])
            rotated += 1

        verb = "would rotate" if options["dry_run"] else "rotated"
        self.stdout.write(self.style.SUCCESS(f"{verb} {rotated}, skipped {skipped}, failed {failed}."))

        if failed:
            raise CommandError(
                f"{failed} account(s) could not be decrypted with the old key and are unchanged."
            )
