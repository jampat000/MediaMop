from __future__ import annotations

from pathlib import Path

import pytest

from mediamop.platform.suite_settings import update_service


def test_read_updater_token_uses_fallback_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    missing = tmp_path / "missing.secret"
    fallback = tmp_path / "runtime.secret"
    token = "x" * 48
    fallback.write_text(token, encoding="utf-8")

    monkeypatch.setattr(
        "mediamop.platform.suite_settings.update_service._updater_token_paths",
        lambda _settings=None: [missing, fallback],
    )

    assert update_service._read_updater_token() == token


def test_windows_updater_service_ready_requires_authenticated_status(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}

    class _Resp:
        status_code = 200

    def _fake_get(url: str, *, headers: dict[str, str] | None = None, timeout: float | None = None) -> _Resp:
        observed["url"] = url
        observed["headers"] = headers
        observed["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr("mediamop.platform.suite_settings.update_service.os.name", "nt", raising=False)
    monkeypatch.setattr(
        "mediamop.platform.suite_settings.update_service._updater_headers",
        lambda _settings=None: {"X-MediaMop-Updater-Token": "token-value"},
    )
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service.httpx.get", _fake_get)

    assert update_service._windows_updater_service_ready() is True
    assert observed["url"] == f"{update_service._updater_base_url()}/api/v1/status"
    assert observed["headers"] == {"X-MediaMop-Updater-Token": "token-value"}
    assert observed["timeout"] == 3.0


def test_windows_updater_service_ready_false_on_unauthorized(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Resp:
        status_code = 401

    monkeypatch.setattr("mediamop.platform.suite_settings.update_service.os.name", "nt", raising=False)
    monkeypatch.setattr(
        "mediamop.platform.suite_settings.update_service._updater_headers",
        lambda _settings=None: {"X-MediaMop-Updater-Token": "bad-token"},
    )
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service.httpx.get", lambda *_args, **_kwargs: _Resp())

    assert update_service._windows_updater_service_ready() is False
