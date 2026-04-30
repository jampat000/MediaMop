"""Fernet encryption for Subber-stored credentials (OpenSubtitles, Sonarr, Radarr)."""

from __future__ import annotations

import base64
import json
from typing import Literal

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from mediamop.core.config import MediaMopSettings
from mediamop.core.credentials_rotation import credential_secret_candidates

_HKDF_INFO = b"mediamop.subber.credentials.v1.fernet"
_ENVELOPE_VERSION = 3
_CREDENTIALS_KEY_ID = "credentials:hkdf:v1"
_CREDENTIALS_KEY_ID_LEGACY = "credentials:v1"
_SESSION_LEGACY_KEY_ID = "session-legacy:v1"


def _fernet_for_secret_hkdf(secret: str | None) -> Fernet | None:
    raw = (secret or "").strip()
    if not raw:
        return None
    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
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


def _active_fernet(settings: MediaMopSettings) -> tuple[Fernet | None, Literal["credentials:hkdf:v1", "session-legacy:v1"]]:
    f = _fernet_for_secret_hkdf(settings.credentials_secret)
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
    f, key_id = _active_fernet(settings)
    if f is None:
        msg = "Cannot store Subber credentials until MEDIAMOP_CREDENTIALS_SECRET or MEDIAMOP_SESSION_SECRET is set."
        raise ValueError(msg)
    token = f.encrypt(plaintext_json.encode("utf-8")).decode("ascii")
    return json.dumps({"version": _ENVELOPE_VERSION, "key_id": key_id, "token": token}, separators=(",", ":"))


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
        if key_id == _CREDENTIALS_KEY_ID:
            fernets = credential_secret_candidates(settings, _fernet_for_secret_hkdf)
        elif key_id == _CREDENTIALS_KEY_ID_LEGACY:
            fernets = credential_secret_candidates(settings, _fernet_for_secret_legacy)
        else:
            fernets = [f for f in [_legacy_fernet(settings)] if f]
        for f in fernets:
            try:
                return f.decrypt(token.encode("ascii")).decode("utf-8")
            except (InvalidToken, ValueError, TypeError):
                continue
        return None
    f = _legacy_fernet(settings)
    if f is None:
        return None
    try:
        return f.decrypt(raw.encode("ascii")).decode("utf-8")
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
    out = {k: "" for k in fields}
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
