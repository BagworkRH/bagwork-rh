"""Secret handling utilities for OAuth credentials (Spec 02/03).

Tokens are encrypted at rest with AES-256-GCM. The key is derived (SHA-256) from
`SOCIAL_ENCRYPTION_KEY` when set, falling back to `SECRET_KEY` so existing
installs keep working. A dedicated key is preferred: rotating `SECRET_KEY` is
routine, and it must not silently render every stored OAuth token undecryptable.

Rotate with `manage.py rotate_social_credentials`, which re-encrypts every stored
row from the old key material to the new one. Raw tokens are never logged.
"""
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings


def key_from_material(material: str) -> bytes:
    """Derive a 32-byte AES-256 key from a secret string."""
    return hashlib.sha256(material.encode("utf-8")).digest()


def current_key() -> bytes:
    """The key new credentials are encrypted with (see module docstring)."""
    material = getattr(settings, "SOCIAL_ENCRYPTION_KEY", "") or settings.SECRET_KEY
    return key_from_material(material)


def encrypt_secret(value: str, key: bytes | None = None):
    """Return (ciphertext, iv) for an OAuth credential string.

    `key` overrides the current key; the rotation command uses it to re-encrypt
    under the new key without mutating global settings.
    """
    key = key or current_key()
    iv = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(iv, value.encode("utf-8"), None)
    return ciphertext, iv


def decrypt_secret(ciphertext: bytes, iv: bytes, key: bytes | None = None) -> str:
    """Decrypt a previously encrypted credential."""
    key = key or current_key()
    plaintext = AESGCM(key).decrypt(iv, bytes(ciphertext), None)
    return plaintext.decode("utf-8")
