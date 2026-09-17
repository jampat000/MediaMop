from __future__ import annotations

import json

from weir.core.config import WeirSettings
from weir.platform.arr_library.arr_connection_crypto import (
    decrypt_arr_api_key,
    encrypt_arr_api_key,
    rewrap_arr_api_key,
)


def _settings(monkeypatch, *, session: str, credentials: str | None) -> WeirSettings:
    monkeypatch.setenv("WEIR_SESSION_SECRET", session)
    if credentials is None:
        monkeypatch.delenv("WEIR_CREDENTIALS_SECRET", raising=False)
    else:
        monkeypatch.setenv("WEIR_CREDENTIALS_SECRET", credentials)
    return WeirSettings.load()


def test_credentials_secret_decouples_arr_from_session_rotation(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WEIR_HOME", str(tmp_path))
    s1 = _settings(
        monkeypatch, session="session-secret-a-abcdefghijklmnopqrstuvwxyz", credentials="credentials-secret-a"
    )

    arr = encrypt_arr_api_key(s1, "arr-key")

    s2 = _settings(
        monkeypatch, session="session-secret-b-abcdefghijklmnopqrstuvwxyz", credentials="credentials-secret-a"
    )

    assert decrypt_arr_api_key(s2, arr) == "arr-key"
    assert json.loads(arr)["key_id"] == "credentials:v1"


def test_legacy_session_secret_ciphertexts_can_be_rewrapped(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WEIR_HOME", str(tmp_path))
    legacy = _settings(monkeypatch, session="legacy-session-secret-abcdefghijklmnopqrstuvwxyz", credentials=None)

    arr_legacy = encrypt_arr_api_key(legacy, "arr-key")

    migrated = _settings(
        monkeypatch,
        session="legacy-session-secret-abcdefghijklmnopqrstuvwxyz",
        credentials="new-credentials-secret",
    )
    arr_new = rewrap_arr_api_key(migrated, arr_legacy)

    rotated = _settings(
        monkeypatch,
        session="rotated-session-secret-abcdefghijklmnopqrstuvwxyz",
        credentials="new-credentials-secret",
    )
    assert arr_new is not None
    assert decrypt_arr_api_key(rotated, arr_new) == "arr-key"


def test_previous_credentials_secret_allows_safe_secret_rotation(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WEIR_HOME", str(tmp_path))
    old = _settings(
        monkeypatch, session="session-secret-a-abcdefghijklmnopqrstuvwxyz", credentials="old-credentials-secret"
    )

    arr = encrypt_arr_api_key(old, "arr-key")

    monkeypatch.setenv("WEIR_SESSION_SECRET", "session-secret-b-abcdefghijklmnopqrstuvwxyz")
    monkeypatch.setenv("WEIR_CREDENTIALS_SECRET", "new-credentials-secret")
    monkeypatch.setenv("WEIR_PREVIOUS_CREDENTIALS_SECRETS", "old-credentials-secret")
    rotated = WeirSettings.load()

    assert decrypt_arr_api_key(rotated, arr) == "arr-key"

    arr_new = rewrap_arr_api_key(rotated, arr)

    monkeypatch.setenv("WEIR_PREVIOUS_CREDENTIALS_SECRETS", "")
    new_only = WeirSettings.load()
    assert arr_new is not None
    assert decrypt_arr_api_key(new_only, arr_new) == "arr-key"
