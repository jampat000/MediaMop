from __future__ import annotations

import json

from mediamop.core.config import MediaMopSettings
from mediamop.modules.pruner.pruner_credentials_crypto import (
    decrypt_pruner_credentials_json,
    encrypt_pruner_credentials_json,
    rewrap_pruner_credentials_json,
)
from mediamop.modules.subber.subber_credentials_crypto import (
    decrypt_subber_credentials_json,
    encrypt_subber_credentials_json,
    rewrap_subber_credentials_json,
)
from mediamop.platform.arr_library.arr_connection_crypto import (
    decrypt_arr_api_key,
    encrypt_arr_api_key,
    rewrap_arr_api_key,
)


def _settings(monkeypatch, *, session: str, credentials: str | None) -> MediaMopSettings:
    monkeypatch.setenv("MEDIAMOP_SESSION_SECRET", session)
    if credentials is None:
        monkeypatch.delenv("MEDIAMOP_CREDENTIALS_SECRET", raising=False)
    else:
        monkeypatch.setenv("MEDIAMOP_CREDENTIALS_SECRET", credentials)
    return MediaMopSettings.load()


def test_credentials_secret_decouples_pruner_subber_and_arr_from_session_rotation(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MEDIAMOP_HOME", str(tmp_path))
    s1 = _settings(monkeypatch, session="session-secret-a-abcdefghijklmnopqrstuvwxyz", credentials="credentials-secret-a")

    pruner = encrypt_pruner_credentials_json(s1, '{"api_key":"p"}')
    subber = encrypt_subber_credentials_json(s1, '{"api_key":"s"}')
    arr = encrypt_arr_api_key(s1, "arr-key")

    s2 = _settings(monkeypatch, session="session-secret-b-abcdefghijklmnopqrstuvwxyz", credentials="credentials-secret-a")

    assert decrypt_pruner_credentials_json(s2, pruner) == '{"api_key":"p"}'
    assert decrypt_subber_credentials_json(s2, subber) == '{"api_key":"s"}'
    assert decrypt_arr_api_key(s2, arr) == "arr-key"
    assert json.loads(pruner)["key_id"] == "credentials:v1"
    assert json.loads(subber)["key_id"] == "credentials:v1"
    assert json.loads(arr)["key_id"] == "credentials:v1"


def test_legacy_session_secret_ciphertexts_can_be_rewrapped(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MEDIAMOP_HOME", str(tmp_path))
    legacy = _settings(monkeypatch, session="legacy-session-secret-abcdefghijklmnopqrstuvwxyz", credentials=None)

    pruner_legacy = encrypt_pruner_credentials_json(legacy, '{"api_key":"p"}')
    subber_legacy = encrypt_subber_credentials_json(legacy, '{"api_key":"s"}')
    arr_legacy = encrypt_arr_api_key(legacy, "arr-key")

    migrated = _settings(
        monkeypatch,
        session="legacy-session-secret-abcdefghijklmnopqrstuvwxyz",
        credentials="new-credentials-secret",
    )
    pruner_new = rewrap_pruner_credentials_json(migrated, pruner_legacy)
    subber_new = rewrap_subber_credentials_json(migrated, subber_legacy)
    arr_new = rewrap_arr_api_key(migrated, arr_legacy)

    rotated = _settings(
        monkeypatch,
        session="rotated-session-secret-abcdefghijklmnopqrstuvwxyz",
        credentials="new-credentials-secret",
    )
    assert pruner_new is not None
    assert subber_new is not None
    assert arr_new is not None
    assert decrypt_pruner_credentials_json(rotated, pruner_new) == '{"api_key":"p"}'
    assert decrypt_subber_credentials_json(rotated, subber_new) == '{"api_key":"s"}'
    assert decrypt_arr_api_key(rotated, arr_new) == "arr-key"
