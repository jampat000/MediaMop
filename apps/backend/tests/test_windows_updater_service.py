from __future__ import annotations

import json
import threading
from pathlib import Path

from fastapi.testclient import TestClient

from mediamop.windows import updater_service


def _configure_runtime_home(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIAMOP_HOME", str(tmp_path))


def test_apply_update_releases_lock_when_thread_start_fails(tmp_path: Path, monkeypatch) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    monkeypatch.setattr(updater_service, "_JOB_LOCK", threading.Lock())
    monkeypatch.setattr(updater_service.os, "name", "nt")
    monkeypatch.setattr(updater_service, "_load_or_create_token", lambda: "token")
    monkeypatch.setattr(updater_service, "_validate_installer_url", lambda url: url)

    class _BrokenThread:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            pass

        def start(self) -> None:
            raise RuntimeError("thread start failed")

    monkeypatch.setattr(updater_service.threading, "Thread", _BrokenThread)

    app = updater_service.create_updater_app()
    with TestClient(app) as client:
        res = client.post(
            "/api/v1/apply",
            headers={"X-MediaMop-Updater-Token": "token"},
            json={
                "installer_url": "https://github.com/jampat000/MediaMop/releases/download/v2.0.3/MediaMopSetup.exe",
                "target_version": "2.0.3",
            },
        )

    assert res.status_code == 500
    assert updater_service._JOB_LOCK.locked() is False


def test_apply_update_job_marks_completed_when_installer_finishes_with_log(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    installer = tmp_path / "MediaMopSetup.exe"
    installer.write_bytes(b"installer")

    def _download(_installer_url: str, _target_version: str) -> Path:
        return installer

    class _DoneProcess:
        pid = 4321

        def wait(self, timeout: float) -> int:
            updater_service._setup_log_path().write_text("installer log", encoding="utf-8")
            return 0

    monkeypatch.setattr(updater_service, "_download_installer", _download)
    monkeypatch.setattr(updater_service, "_launch_installer_detached", lambda _path: _DoneProcess())

    updater_service._apply_update_job("https://example.invalid/MediaMopSetup.exe", "2.0.3")
    state = updater_service._read_state()

    assert state["phase"] == "completed"
    assert state["target_version"] == "2.0.3"
    assert state["last_error"] is None
    assert state["installer_log_path"] == str(updater_service._setup_log_path())


def test_apply_update_job_marks_failed_when_installer_log_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    installer = tmp_path / "MediaMopSetup.exe"
    installer.write_bytes(b"installer")

    def _download(_installer_url: str, _target_version: str) -> Path:
        return installer

    class _DoneProcessNoLog:
        pid = 6789

        def wait(self, timeout: float) -> int:
            return 0

    monkeypatch.setattr(updater_service, "_download_installer", _download)
    monkeypatch.setattr(updater_service, "_launch_installer_detached", lambda _path: _DoneProcessNoLog())

    updater_service._apply_update_job("https://example.invalid/MediaMopSetup.exe", "2.0.3")
    state = updater_service._read_state()

    assert state["phase"] == "failed"
    assert state["target_version"] == "2.0.3"
    assert "did not produce installer-latest.log" in str(state["last_error"])


def test_read_state_surfaces_state_corruption(tmp_path: Path, monkeypatch) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    state_path = updater_service._state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text("{bad json", encoding="utf-8")

    state = updater_service._read_state()

    assert state["phase"] == "state_corrupt"
    assert "Could not parse updater state file" in str(state["last_error"])


def test_read_state_merges_valid_json(tmp_path: Path, monkeypatch) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    state_path = updater_service._state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"phase": "installer_running", "target_version": "2.0.3"}),
        encoding="utf-8",
    )

    state = updater_service._read_state()

    assert state["phase"] == "installer_running"
    assert state["target_version"] == "2.0.3"
    assert state["installer_log_path"] == str(updater_service._setup_log_path())
