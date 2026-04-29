"""Provider-neutral Pruner credentials envelope — JSON encrypted at rest (see migration + crypto)."""

from __future__ import annotations

import json
from typing import Any, Literal

from mediamop.core.config import MediaMopSettings
from mediamop.modules.pruner.pruner_credentials_crypto import (
    decrypt_pruner_credentials_json,
    encrypt_pruner_credentials_json,
)

PrunerProvider = Literal["emby", "jellyfin", "plex"]

CURRENT_ENVELOPE_VERSION = 1


def build_envelope_for_storage(*, provider: PrunerProvider, secrets: dict[str, str]) -> str:
    """Return canonical JSON string (before encryption) for the given provider."""

    body: dict[str, Any] = {
        "version": CURRENT_ENVELOPE_VERSION,
        "key_id": "provider-secrets:v1",
        "provider": provider,
        "secrets": dict(secrets),
    }
    return json.dumps(body, separators=(",", ":"), sort_keys=True)


def encrypt_envelope(settings: MediaMopSettings, *, provider: PrunerProvider, secrets: dict[str, str]) -> str:
    return encrypt_pruner_credentials_json(settings, build_envelope_for_storage(provider=provider, secrets=secrets))


def parse_envelope_plaintext(plaintext_json: str) -> dict[str, Any]:
    data = json.loads(plaintext_json)
    if not isinstance(data, dict):
        msg = "Pruner credentials envelope must be a JSON object"
        raise ValueError(msg)
    ver = data.get("version")
    if ver != CURRENT_ENVELOPE_VERSION:
        msg = f"Unsupported Pruner credentials envelope version: {ver!r}"
        raise ValueError(msg)
    prov = data.get("provider")
    if prov not in ("emby", "jellyfin", "plex"):
        msg = f"Invalid Pruner credentials provider: {prov!r}"
        raise ValueError(msg)
    sec = data.get("secrets")
    if not isinstance(sec, dict):
        msg = "Pruner credentials envelope.secrets must be an object"
        raise ValueError(msg)
    secrets = {str(k): str(v) for k, v in sec.items()}
    return {"version": int(ver), "key_id": str(data.get("key_id") or "legacy"), "provider": prov, "secrets": secrets}


def decrypt_and_parse_envelope(settings: MediaMopSettings, ciphertext: str) -> dict[str, Any] | None:
    plain = decrypt_pruner_credentials_json(settings, ciphertext)
    if plain is None:
        return None
    return parse_envelope_plaintext(plain)


def envelope_secrets_for_provider(provider: str, secrets: dict[str, str]) -> dict[str, str]:
    """Normalize wire ``credentials`` object into stored ``secrets`` (additive keys, no churn)."""

    if provider in ("emby", "jellyfin"):
        key = secrets.get("api_key")
        if not key or not str(key).strip():
            msg = "credentials.api_key is required for Emby and Jellyfin"
            raise ValueError(msg)
        return {"api_key": str(key).strip()}
    if provider == "plex":
        token = secrets.get("auth_token") or secrets.get("plex_token")
        if not token or not str(token).strip():
            msg = "credentials.auth_token (or legacy credentials.plex_token) is required for Plex"
            raise ValueError(msg)
        out = {"auth_token": str(token).strip()}
        cid = secrets.get("client_identifier")
        if cid and str(cid).strip():
            out["client_identifier"] = str(cid).strip()
        return out
    msg = f"Unknown provider: {provider!r}"
    raise ValueError(msg)
