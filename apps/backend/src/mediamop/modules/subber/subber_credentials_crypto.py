"""Fernet encryption for Subber-stored credentials (OpenSubtitles, Sonarr, Radarr)."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from mediamop.core.config import MediaMopSettings


def _fernet(settings: MediaMopSettings) -> Fernet | None:
    secret = (settings.session_secret or "").strip()
    if not secret:
        return None
    digest = hashlib.sha256(b"mediamop.subber.credentials.v1|" + secret.encode()).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_subber_credentials_json(settings: MediaMopSettings, plaintext_json: str) -> str:
    f = _fernet(settings)
    if f is None:
        msg = "Cannot store Subber credentials until MEDIAMOP_SESSION_SECRET is set on the server."
        raise ValueError(msg)
    return f.encrypt(plaintext_json.encode("utf-8")).decode("ascii")


def decrypt_subber_credentials_json(settings: MediaMopSettings, ciphertext: str) -> str | None:
    f = _fernet(settings)
    if f is None:
        return None
    raw = (ciphertext or "").strip()
    if not raw:
        return None
    try:
        return f.decrypt(raw.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return None
