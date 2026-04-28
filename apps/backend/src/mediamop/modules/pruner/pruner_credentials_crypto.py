"""Fernet encryption for Pruner server credentials JSON."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Literal

from cryptography.fernet import Fernet, InvalidToken

from mediamop.core.config import MediaMopSettings

_DOMAIN = b"mediamop.pruner.credentials.v1|"
_ENVELOPE_VERSION = 2
_CREDENTIALS_KEY_ID = "credentials:v1"
_SESSION_LEGACY_KEY_ID = "session-legacy:v1"


def _fernet_for_secret(secret: str | None) -> Fernet | None:
    raw = (secret or "").strip()
    if not raw:
        return None
    digest = hashlib.sha256(_DOMAIN + raw.encode()).digest()
    key = base64.urlsafe_b64encode(digest)
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


def encrypt_pruner_credentials_json(settings: MediaMopSettings, plaintext_json: str) -> str:
    """Encrypt UTF-8 JSON text for ``pruner_server_instances.credentials_ciphertext``."""

    f, key_id = _active_fernet(settings)
    if f is None:
        msg = "Cannot store Pruner credentials until MEDIAMOP_CREDENTIALS_SECRET or MEDIAMOP_SESSION_SECRET is set."
        raise ValueError(msg)
    token = f.encrypt(plaintext_json.encode("utf-8")).decode("ascii")
    return json.dumps({"version": _ENVELOPE_VERSION, "key_id": key_id, "token": token}, separators=(",", ":"))


def decrypt_pruner_credentials_json(settings: MediaMopSettings, ciphertext: str) -> str | None:
    """Decrypt stored JSON, supporting v2 credential envelopes and legacy raw session-secret tokens."""

    env = _decode_envelope(ciphertext)
    if env is not None:
        token = str(env.get("token") or "")
        key_id = str(env.get("key_id") or "")
        if not token:
            return None
        f = _fernet_for_secret(settings.credentials_secret) if key_id == _CREDENTIALS_KEY_ID else _legacy_fernet(settings)
        if f is None:
            return None
        try:
            return f.decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError, TypeError):
            return None

    f = _legacy_fernet(settings)
    if f is None:
        return None
    try:
        return f.decrypt((ciphertext or "").strip().encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return None


def rewrap_pruner_credentials_json(settings: MediaMopSettings, ciphertext: str) -> str | None:
    """Return a credentials-secret envelope for readable legacy ciphertext, or ``None`` if not possible."""

    if not settings.credentials_secret:
        return None
    plain = decrypt_pruner_credentials_json(settings, ciphertext)
    if plain is None:
        return None
    return encrypt_pruner_credentials_json(settings, plain)
