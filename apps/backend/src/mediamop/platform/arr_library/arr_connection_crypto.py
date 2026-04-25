"""Encrypt/decrypt Sonarr/Radarr API keys at rest (Fernet key derived from ``MEDIAMOP_SESSION_SECRET``)."""

from __future__ import annotations

import base64
import binascii

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from mediamop.core.config import MediaMopSettings

# Frozen KDF domain bytes (legacy install compatibility). Do not change.
_ARR_API_KEY_KDF_PEPPER = binascii.a2b_hex(
    "6d656469616d6f702e666574636865722e6172725f6170695f6b65792e76317c"
)
_ARR_API_KEY_KDF_ITERATIONS = 390_000


def _fernet(settings: MediaMopSettings) -> Fernet | None:
    secret = (settings.session_secret or "").strip()
    if not secret:
        return None
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_ARR_API_KEY_KDF_PEPPER,
        iterations=_ARR_API_KEY_KDF_ITERATIONS,
    )
    key = base64.urlsafe_b64encode(kdf.derive(secret.encode("utf-8")))
    return Fernet(key)


def encrypt_arr_api_key(settings: MediaMopSettings, plaintext: str) -> str:
    """Encrypt API key for SQLite storage. Requires a configured session secret."""

    f = _fernet(settings)
    if f is None:
        msg = "Cannot save library API keys until MEDIAMOP_SESSION_SECRET is set on the server."
        raise ValueError(msg)
    return f.encrypt(plaintext.strip().encode("utf-8")).decode("ascii")


def decrypt_arr_api_key(settings: MediaMopSettings, ciphertext: str) -> str | None:
    """Decrypt stored API key, or ``None`` if secret missing or ciphertext invalid."""

    f = _fernet(settings)
    if f is None:
        return None
    try:
        return f.decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return None
