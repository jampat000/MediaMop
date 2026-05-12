"""Fernet encryption for Subber-stored credentials (OpenSubtitles, Sonarr, Radarr)."""

from __future__ import annotations

import base64
import json
import os
from typing import Literal

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from mediamop.core.config import MediaMopSettings
from mediamop.core.credentials_rotation import credential_secret_candidates

_HKDF_INFO = b"mediamop.subber.credentials.v1.fernet"
_ENVELOPE_VERSION = 4
_CREDENTIALS_KEY_ID: Literal["credentials:hkdf:v1"] = "credentials:hkdf:v1"
_CREDENTIALS_KEY_ID_LEGACY = "credentials:v1"
_SESSION_LEGACY_KEY_ID: Literal["session-legacy:v1"] = "session-legacy:v1"


def _fernet_for_secret_hkdf(secret: str | None, *, salt: bytes | None = None) -> Fernet | None:
    raw = (secret or "").strip()
    if not raw:
        return None
    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=_HKDF_INFO,
    ).derive(raw.encode("utf-8"))
    key = base64.urlsafe_b64encode(derived)
    return Fernet(key)


def _fernet_for_secret_legacy(secret: str | None) -> Fernet | None:
    raw = (secret or "").strip()
    if not raw:
        return None
    digest = hashes.Hash(hashes.SHA256())
    digest.update(b"mediamop.subber.credentials.v1|")
    digest.update(raw.encode("utf-8"))
    key = base64.urlsafe_b64encode(digest.finalize())
    return Fernet(key)


def _active_fernet(
    settings: MediaMopSettings,
    *,
    salt: bytes,
) -> tuple[Fernet | None, Literal["credentials:hkdf:v1", "session-legacy:v1"]]:
    f = _fernet_for_secret_hkdf(settings.credentials_secret, salt=salt)
    if f is not None:
        return f, _CREDENTIALS_KEY_ID
    return _fernet_for_secret_legacy(settings.session_secret), _SESSION_LEGACY_KEY_ID


def _legacy_fernet(settings: MediaMopSettings) -> Fernet | None:
    return _fernet_for_secret_legacy(settings.session_secret)


def _decode_envelope(ciphertext: str) -> dict[str, object] | None:
    raw = (ciphertext or "").strip()
    if not raw.startswith("{"):
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def encrypt_subber_credentials_json(settings: MediaMopSettings, plaintext_json: str) -> str:
    salt = os.urandom(16)
    f, key_id = _active_fernet(settings, salt=salt)
    if f is None:
        msg = "Cannot store Subber credentials until MEDIAMOP_CREDENTIALS_SECRET or MEDIAMOP_SESSION_SECRET is set."
        raise ValueError(msg)
    token = f.encrypt(plaintext_json.encode("utf-8")).decode("ascii")
    salt_b64 = base64.urlsafe_b64encode(salt).decode("ascii")
    return json.dumps(
        {"version": _ENVELOPE_VERSION, "key_id": key_id, "salt": salt_b64, "token": token},
        separators=(",", ":"),
    )


def decrypt_subber_credentials_json(settings: MediaMopSettings, ciphertext: str) -> str | None:
    raw = (ciphertext or "").strip()
    if not raw:
        return None
    env = _decode_envelope(raw)
    if env is not None:
        token = str(env.get("token") or "")
        key_id = str(env.get("key_id") or "")
        if not token:
            return None
        fernets: list[Fernet]
        if key_id == _CREDENTIALS_KEY_ID:
            salt_b64 = env.get("salt")
            salt: bytes | None = None
            if salt_b64 and isinstance(salt_b64, str):
                try:
                    salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
                except Exception:
                    salt = None
            fernets = credential_secret_candidates(
                settings, lambda s, _salt=salt: _fernet_for_secret_hkdf(s, salt=_salt)  # type: ignore[misc]
            )
        elif key_id == _CREDENTIALS_KEY_ID_LEGACY:
            fernets = credential_secret_candidates(settings, _fernet_for_secret_legacy)
        else:
            fernets = [candidate for candidate in [_legacy_fernet(settings)] if candidate is not None]
        for fernet in fernets:
            try:
                return fernet.decrypt(token.encode("ascii")).decode("utf-8")
            except (InvalidToken, ValueError, TypeError):
                continue
        return None
    legacy_fernet = _legacy_fernet(settings)
    if legacy_fernet is None:
        return None
    try:
        return legacy_fernet.decrypt(raw.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return None


def rewrap_subber_credentials_json(settings: MediaMopSettings, ciphertext: str) -> str | None:
    if not settings.credentials_secret:
        return None
    plain = decrypt_subber_credentials_json(settings, ciphertext)
    if plain is None:
        return None
    return encrypt_subber_credentials_json(settings, plain)


def build_provider_credentials_plaintext(provider_key: str, secrets: dict[str, str | None]) -> str:
    """JSON envelope for ``subber_providers.credentials_ciphertext`` (encrypted by caller).

    ``secrets`` keys must match :data:`~mediamop.modules.subber.subber_provider_registry.PROVIDER_CREDENTIAL_FIELDS`.
    """

    from mediamop.modules.subber.subber_provider_registry import PROVIDER_CREDENTIAL_FIELDS

    fields = PROVIDER_CREDENTIAL_FIELDS.get(provider_key, [])
    sec: dict[str, str] = {}
    for k in fields:
        v = secrets.get(k)
        sec[k] = str(v).strip() if v is not None else ""
    return json.dumps({"provider": provider_key, "secrets": sec}, separators=(",", ":"))


def parse_provider_secrets_json(provider_key: str, plaintext: str | None) -> dict[str, str]:
    """Parse decrypted JSON; returns empty strings for missing keys."""

    from mediamop.modules.subber.subber_provider_registry import PROVIDER_CREDENTIAL_FIELDS

    fields = PROVIDER_CREDENTIAL_FIELDS.get(provider_key, [])
    out = dict.fromkeys(fields, "")
    if not plaintext or not plaintext.strip():
        return out
    try:
        data = json.loads(plaintext)
    except json.JSONDecodeError:
        return out
    if not isinstance(data, dict):
        return out
    raw = data.get("secrets")
    if not isinstance(raw, dict):
        return out
    for k in fields:
        out[k] = str(raw.get(k) or "").strip()
    return out
