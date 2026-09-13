"""Secret handling utilities for X OAuth credentials (Spec 02/03).

Chosen AES-256-GCM encryption via the `cryptography` library. The encryption
key is derived from SECRET_KEY at runtime; raw tokens are never stored.
"""
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings


def _derive_key() -> bytes:
    """Derive a 32-byte key from SECRET_KEY using SHA-256."""
    material = settings.SECRET_KEY.encode("utf-8")
    return hashlib.sha256(material).digest()


def encrypt_secret(value: str):
    """Return (ciphertext, iv) for an OAuth credential string."""
    key = _derive_key()
    iv = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(iv, value.encode("utf-8"), None)
    return ciphertext, iv


def decrypt_secret(ciphertext: bytes, iv: bytes) -> str:
    """Decrypt a previously encrypted credential."""
    key = _derive_key()
    plaintext = AESGCM(key).decrypt(iv, ciphertext, None)
    return plaintext.decode("utf-8")