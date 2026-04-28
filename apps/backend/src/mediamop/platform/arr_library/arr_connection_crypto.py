"""Encrypt/decrypt Sonarr/Radarr API keys at rest."""

from __future__ import annotations

import base64
import binascii
import json
from typing import Literal

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from mediamop.core.config import MediaMopSettings

# Frozen KDF domain bytes (legacy install compatibility). Do not change.
_ARR_API_KEY_KDF_PEPPER = binascii.a2b_hex(
    "6d656469616d6f702e666574636865722e6172725f6170695f6b65792e76317c"
)
_ARR_API_KEY_KDF_ITERATIONS = 390_000
_ENVELOPE_VERSION = 2
_CREDENTIALS_KEY_ID = "credentials:v1"
_SESSION_LEGACY_KEY_ID = "session-legacy:v1"


def _fernet_for_secret(secret: str | None) -> Fernet | None:
    raw = (secret or "").strip()
    if not raw:
        return None
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_ARR_API_KEY_KDF_PEPPER,
        iterations=_ARR_API_KEY_KDF_ITERATIONS,
    )
    key = base64.urlsafe_b64encode(kdf.derive(raw.encode("utf-8")))
    return Fernet(key)


def _active_fernet(settings: MediaMopSettings) -> tuple[Fernet | None, Literal["credentials:v1", "session-legacy:v1"]]:
    f = _fernet_for_secret(settings.credentials_secret)
    if f is not None:
        return f, _CREDENTIALS_KEY_ID
    return _fernet_for_secret(settings.session_secret), _SESSION_LEGACY_KEY_ID


def _legacy_fernet(settings: MediaMopSettings) -> Fernet | None:
    return _fernet_for_secret(settings.session_secret)


def _decode_envelope(ciphertext: str) -> dict[str, object] | None:
    raw = (ciphertext or "").strip()
    if not raw.startswith("{"):
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def encrypt_arr_api_key(settings: MediaMopSettings, plaintext: str) -> str:
    """Encrypt API key for SQLite storage."""

    f, key_id = _active_fernet(settings)
    if f is None:
        msg = "Cannot save library API keys until MEDIAMOP_CREDENTIALS_SECRET or MEDIAMOP_SESSION_SECRET is set."
        raise ValueError(msg)
    token = f.encrypt(plaintext.strip().encode("utf-8")).decode("ascii")
    return json.dumps({"version": _ENVELOPE_VERSION, "key_id": key_id, "token": token}, separators=(",", ":"))


def decrypt_arr_api_key(settings: MediaMopSettings, ciphertext: str) -> str | None:
    """Decrypt stored API key, supporting v2 credential envelopes and legacy raw session-secret tokens."""

    raw = (ciphertext or "").strip()
    if not raw:
        return None
    env = _decode_envelope(raw)
    if env is not None:
        token = str(env.get("token") or "")
        key_id = str(env.get("key_id") or "")
        f = _fernet_for_secret(settings.credentials_secret) if key_id == _CREDENTIALS_KEY_ID else _legacy_fernet(settings)
        if f is None or not token:
            return None
        try:
            return f.decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError, TypeError):
            return None
    f = _legacy_fernet(settings)
    if f is None:
        return None
    try:
        return f.decrypt(raw.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return None


def rewrap_arr_api_key(settings: MediaMopSettings, ciphertext: str) -> str | None:
    if not settings.credentials_secret:
        return None
    plain = decrypt_arr_api_key(settings, ciphertext)
    if plain is None:
        return None
    return encrypt_arr_api_key(settings, plain)
