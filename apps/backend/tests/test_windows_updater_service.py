from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mediamop.windows import updater_service


def _configure_runtime_home(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIAMOP_HOME", str(tmp_path))


def _release_with_assets(
    version: str,
    asset_names: set[str] | None = None,
):
    names = asset_names or {
        "MediaMopSetup.exe",
        "MediaMopSetup.exe.sha256",
    }

    class _Release:
        def asset_named(self, name: str):
            if name not in names:
                return None
            return type(
                "Asset",
                (),
                {
                    "browser_download_url": f"https://github.com/jampat000/MediaMop/releases/download/v{version}/{name}",
                },
            )()

    return _Release()


def test_apply_update_rejects_legacy_installer_url_payload(tmp_path: Path, monkeypatch) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    with monkeypatch.context() as scoped:
        scoped.setattr(updater_service.os, "name", "nt")
        scoped.setattr(updater_service, "_load_or_create_token", lambda: "token")
        app = updater_service.create_updater_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            res = client.post(
                "/api/v1/apply",
                headers={"X-MediaMop-Updater-Token": "token"},
                json={
                    "installer_url": "https://github.com/jampat000/MediaMop/releases/download/v2.0.8/MediaMopSetup.exe",
                    "target_version": "2.0.8",
                },
            )

    assert res.status_code == 422


def test_apply_update_marks_failed_when_helper_launch_fails(tmp_path: Path, monkeypatch) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    with monkeypatch.context() as scoped:
        scoped.setattr(updater_service.os, "name", "nt")
        scoped.setattr(updater_service, "_load_or_create_token", lambda: "token")
        scoped.setattr(updater_service, "_launch_helper", lambda _attempt_id: (_ for _ in ()).throw(RuntimeError("boom")))
        app = updater_service.create_updater_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            res = client.post(
                "/api/v1/apply",
                headers={"X-MediaMop-Updater-Token": "token"},
                json={"target_version": "2.0.8"},
            )

    state = updater_service._read_state()
    assert res.status_code == 500
    assert state["phase"] == "failed"
    assert "Could not launch upgrade helper" in str(state["last_error"])


def test_apply_update_starts_helper_and_returns_attempt_id(tmp_path: Path, monkeypatch) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)

    class _Helper:
        pid = 4321

    with monkeypatch.context() as scoped:
        scoped.setattr(updater_service.os, "name", "nt")
        scoped.setattr(updater_service, "_load_or_create_token", lambda: "token")
        scoped.setattr(updater_service, "_launch_helper", lambda _attempt_id: _Helper())
        scoped.setattr(updater_service.uuid, "uuid4", lambda: type("Uuid", (), {"hex": "attempt-123"})())
        app = updater_service.create_updater_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            res = client.post(
                "/api/v1/apply",
                headers={"X-MediaMop-Updater-Token": "token"},
                json={"target_version": "v2.0.8"},
            )

    body = res.json()
    state = updater_service._read_state()
    assert res.status_code == 200
    assert body["accepted"] is True
    assert body["attempt_id"] == "attempt-123"
    assert body["target_version"] == "2.0.8"
    assert state["attempt_id"] == "attempt-123"
    assert state["target_version"] == "2.0.8"
    assert state["diagnostics"]["helper_pid"] == 4321


def test_process_matches_attempt_rejects_reused_pid_with_wrong_path(monkeypatch) -> None:
    started_at = datetime(2026, 5, 7, 4, 39, 51, tzinfo=UTC)
    monkeypatch.setattr(
        updater_service,
        "_read_process_snapshot",
        lambda _pid: {
            "pid": 4321,
            "executable_path": r"C:\Windows\System32\notepad.exe",
            "command_line": r'"C:\Windows\System32\notepad.exe"',
            "creation_time_utc": (started_at + timedelta(seconds=20)).isoformat(),
        },
    )

    assert (
        updater_service._process_matches_attempt(
            4321,
            expected_path=r"C:\ProgramData\MediaMop\upgrades\MediaMopSetup-2.1.0.exe",
            attempt_started_at=started_at,
        )
        is False
    )


def test_process_matches_attempt_rejects_matching_path_with_older_creation_time(monkeypatch) -> None:
    started_at = datetime(2026, 5, 7, 4, 39, 51, tzinfo=UTC)
    expected_path = r"C:\ProgramData\MediaMop\upgrades\MediaMopSetup-2.1.0.exe"
    monkeypatch.setattr(
        updater_service,
        "_read_process_snapshot",
        lambda _pid: {
            "pid": 4321,
            "executable_path": expected_path,
            "command_line": f'"{expected_path}" /VERYSILENT',
            "creation_time_utc": (started_at - timedelta(minutes=5)).isoformat(),
        },
    )

    assert (
        updater_service._process_matches_attempt(
            4321,
            expected_path=expected_path,
            attempt_started_at=started_at,
        )
        is False
    )


def test_process_matches_attempt_accepts_matching_path_after_attempt_start(monkeypatch) -> None:
    started_at = datetime(2026, 5, 7, 4, 39, 51, tzinfo=UTC)
    expected_path = r"C:\ProgramData\MediaMop\upgrades\MediaMopSetup-2.1.0.exe"
    monkeypatch.setattr(
        updater_service,
        "_read_process_snapshot",
        lambda _pid: {
            "pid": 4321,
            "executable_path": expected_path,
            "command_line": f'"{expected_path}" /VERYSILENT',
            "creation_time_utc": (started_at + timedelta(seconds=10)).isoformat(),
        },
    )

    assert (
        updater_service._process_matches_attempt(
            4321,
            expected_path=expected_path,
            attempt_started_at=started_at,
        )
        is True
    )


def test_process_matches_attempt_accepts_matching_command_line_when_path_missing(monkeypatch) -> None:
    started_at = datetime(2026, 5, 7, 4, 39, 51, tzinfo=UTC)
    expected_path = r"C:\ProgramData\MediaMop\upgrades\MediaMopSetup-2.1.0.exe"
    monkeypatch.setattr(
        updater_service,
        "_read_process_snapshot",
        lambda _pid: {
            "pid": 4321,
            "executable_path": None,
            "command_line": f'"{expected_path}" /VERYSILENT',
            "creation_time_utc": (started_at + timedelta(seconds=10)).isoformat(),
        },
    )

    assert (
        updater_service._process_matches_attempt(
            4321,
            expected_path=expected_path,
            attempt_started_at=started_at,
        )
        is True
    )


def test_process_matches_attempt_returns_false_when_snapshot_is_unverifiable(monkeypatch) -> None:
    monkeypatch.setattr(updater_service, "_read_process_snapshot", lambda _pid: None)

    assert (
        updater_service._process_matches_attempt(
            4321,
            expected_path=r"C:\ProgramData\MediaMop\upgrades\MediaMopSetup-2.1.0.exe",
            attempt_started_at=datetime(2026, 5, 7, 4, 39, 51, tzinfo=UTC),
        )
        is False
    )


def test_perform_upgrade_attempt_marks_completed_only_after_verified_version(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    attempt_id = "attempt-123"
    installer = tmp_path / "MediaMopSetup.exe"
    installer.write_bytes(b"installer")
    updater_service._persist_state(updater_service._fresh_attempt_state("2.0.8", attempt_id))

    class _DoneProcess:
        pid = 6789

        def wait(self, timeout: float) -> int:
            Path(updater_service._read_state()["installer_log_path"]).write_text("installer log", encoding="utf-8")
            return 0

    monkeypatch.setattr(
        updater_service,
        "fetch_release_record_by_version",
        lambda version, user_agent_version: type(
            "Release",
            (),
            {
                "asset_named": lambda self, name: type(
                    "Asset",
                    (),
                    {
                        "browser_download_url": f"https://github.com/jampat000/MediaMop/releases/download/v{version}/{name}",
                    },
                )()
                if name in {"MediaMopSetup.exe", "MediaMopSetup.exe.sha256"}
                else None
            },
        )(),
    )
    monkeypatch.setattr(updater_service, "_download_text", lambda _url: "a" * 64 + "  MediaMopSetup.exe")
    monkeypatch.setattr(updater_service, "_download_installer", lambda _url, target_version, attempt_id: installer)
    monkeypatch.setattr(updater_service, "_sha256_for_path", lambda _path: "a" * 64)
    monkeypatch.setattr(updater_service, "_verify_authenticode_signature", lambda _path: (True, "not required"))
    monkeypatch.setattr(updater_service, "_launch_installer", lambda _path, installer_log_path: _DoneProcess())
    monkeypatch.setattr(
        updater_service,
        "_verify_install",
        lambda target_version: (
            True,
            {"backend_version": target_version, "packaged_version": target_version},
            f"Upgrade completed. Running version: {target_version}.",
        ),
    )

    updater_service._perform_upgrade_attempt(attempt_id)
    state = updater_service._read_state()

    assert state["phase"] == "completed"
    assert state["target_version"] == "2.0.8"
    assert state["current_version_seen"] == "2.0.8"
    assert state["last_error"] is None


def test_perform_upgrade_attempt_marks_failed_when_installer_log_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    attempt_id = "attempt-123"
    installer = tmp_path / "MediaMopSetup.exe"
    installer.write_bytes(b"installer")
    updater_service._persist_state(updater_service._fresh_attempt_state("2.0.8", attempt_id))

    class _DoneProcessNoLog:
        pid = 6789

        def wait(self, timeout: float) -> int:
            return 0

    monkeypatch.setattr(
        updater_service,
        "fetch_release_record_by_version",
        lambda version, user_agent_version: type(
            "Release",
            (),
            {
                "asset_named": lambda self, name: type(
                    "Asset",
                    (),
                    {
                        "browser_download_url": f"https://github.com/jampat000/MediaMop/releases/download/v{version}/{name}",
                    },
                )()
                if name in {"MediaMopSetup.exe", "MediaMopSetup.exe.sha256"}
                else None
            },
        )(),
    )
    monkeypatch.setattr(updater_service, "_download_text", lambda _url: "a" * 64 + "  MediaMopSetup.exe")
    monkeypatch.setattr(updater_service, "_download_installer", lambda _url, target_version, attempt_id: installer)
    monkeypatch.setattr(updater_service, "_sha256_for_path", lambda _path: "a" * 64)
    monkeypatch.setattr(updater_service, "_verify_authenticode_signature", lambda _path: (True, "not required"))
    monkeypatch.setattr(updater_service, "_launch_installer", lambda _path, installer_log_path: _DoneProcessNoLog())

    updater_service._perform_upgrade_attempt(attempt_id)
    state = updater_service._read_state()

    assert state["phase"] == "failed"
    assert "did not produce an installer log" in str(state["last_error"]).lower()


def test_perform_upgrade_attempt_marks_failed_when_version_does_not_change(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    attempt_id = "attempt-123"
    installer = tmp_path / "MediaMopSetup.exe"
    installer.write_bytes(b"installer")
    updater_service._persist_state(updater_service._fresh_attempt_state("2.0.8", attempt_id))

    class _DoneProcess:
        pid = 6789

        def wait(self, timeout: float) -> int:
            Path(updater_service._read_state()["installer_log_path"]).write_text("installer log", encoding="utf-8")
            return 0

    monkeypatch.setattr(
        updater_service,
        "fetch_release_record_by_version",
        lambda version, user_agent_version: type(
            "Release",
            (),
            {
                "asset_named": lambda self, name: type(
                    "Asset",
                    (),
                    {
                        "browser_download_url": f"https://github.com/jampat000/MediaMop/releases/download/v{version}/{name}",
                    },
                )()
                if name in {"MediaMopSetup.exe", "MediaMopSetup.exe.sha256"}
                else None
            },
        )(),
    )
    monkeypatch.setattr(updater_service, "_download_text", lambda _url: "a" * 64 + "  MediaMopSetup.exe")
    monkeypatch.setattr(updater_service, "_download_installer", lambda _url, target_version, attempt_id: installer)
    monkeypatch.setattr(updater_service, "_sha256_for_path", lambda _path: "a" * 64)
    monkeypatch.setattr(updater_service, "_verify_authenticode_signature", lambda _path: (True, "not required"))
    monkeypatch.setattr(updater_service, "_launch_installer", lambda _path, installer_log_path: _DoneProcess())
    monkeypatch.setattr(
        updater_service,
        "_verify_install",
        lambda _target_version: (
            False,
            {"backend_version": "2.0.7", "packaged_version": "2.0.7"},
            "Running backend still reports 2.0.7 instead of 2.0.8.",
        ),
    )

    updater_service._perform_upgrade_attempt(attempt_id)
    state = updater_service._read_state()

    assert state["phase"] == "failed"
    assert "2.0.7 instead of 2.0.8" in str(state["last_error"])


def test_perform_upgrade_attempt_marks_failed_when_installer_exits_nonzero(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    attempt_id = "attempt-123"
    installer = tmp_path / "MediaMopSetup.exe"
    installer.write_bytes(b"installer")
    updater_service._persist_state(updater_service._fresh_attempt_state("2.0.8", attempt_id))

    class _FailedProcess:
        pid = 6789

        def wait(self, timeout: float) -> int:
            Path(updater_service._read_state()["installer_log_path"]).write_text("installer log", encoding="utf-8")
            return 5

    monkeypatch.setattr(
        updater_service,
        "fetch_release_record_by_version",
        lambda version, user_agent_version: _release_with_assets(version),
    )
    monkeypatch.setattr(updater_service, "_download_text", lambda _url: "a" * 64 + "  MediaMopSetup.exe")
    monkeypatch.setattr(updater_service, "_download_installer", lambda _url, target_version, attempt_id: installer)
    monkeypatch.setattr(updater_service, "_sha256_for_path", lambda _path: "a" * 64)
    monkeypatch.setattr(updater_service, "_verify_authenticode_signature", lambda _path: (True, "not required"))
    monkeypatch.setattr(updater_service, "_launch_installer", lambda _path, installer_log_path: _FailedProcess())

    updater_service._perform_upgrade_attempt(attempt_id)
    state = updater_service._read_state()

    assert state["phase"] == "failed"
    assert "installer exited with code 5" in str(state["last_error"]).lower()


def test_perform_upgrade_attempt_requires_checksum_manifest_in_production(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    attempt_id = "attempt-123"
    updater_service._persist_state(updater_service._fresh_attempt_state("2.0.8", attempt_id))

    monkeypatch.delenv("MEDIAMOP_UPDATER_ALLOW_UNVERIFIED", raising=False)
    monkeypatch.setattr(
        updater_service,
        "fetch_release_record_by_version",
        lambda version, user_agent_version: _release_with_assets(
            version,
            {"MediaMopSetup.exe"},
        ),
    )

    updater_service._perform_upgrade_attempt(attempt_id)
    state = updater_service._read_state()

    assert state["phase"] == "failed"
    assert "require mediamopsetup.exe.sha256" in str(state["last_error"]).lower()


def test_perform_upgrade_attempt_fails_on_sha256_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    attempt_id = "attempt-123"
    installer = tmp_path / "MediaMopSetup.exe"
    installer.write_bytes(b"installer")
    updater_service._persist_state(updater_service._fresh_attempt_state("2.0.8", attempt_id))

    monkeypatch.setattr(
        updater_service,
        "fetch_release_record_by_version",
        lambda version, user_agent_version: _release_with_assets(version),
    )
    monkeypatch.setattr(updater_service, "_download_text", lambda _url: "a" * 64 + "  MediaMopSetup.exe")
    monkeypatch.setattr(updater_service, "_download_installer", lambda _url, target_version, attempt_id: installer)
    monkeypatch.setattr(updater_service, "_sha256_for_path", lambda _path: "b" * 64)
    monkeypatch.setattr(updater_service, "_verify_authenticode_signature", lambda _path: (True, "not required"))

    updater_service._perform_upgrade_attempt(attempt_id)
    state = updater_service._read_state()

    assert state["phase"] == "failed"
    assert "sha-256 mismatch" in str(state["last_error"]).lower()


def test_download_installer_streams_response_without_context_manager(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    monkeypatch.setattr(updater_service, "_MIN_INSTALLER_BYTES", 4)

    class _Client:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    class _Response:
        def __init__(self) -> None:
            self.closed = False

        def iter_bytes(self):
            yield b"abcd"
            yield b"efgh"

        def close(self) -> None:
            self.closed = True

    client = _Client()
    response = _Response()
    monkeypatch.setattr(
        updater_service,
        "_open_trusted_download_stream",
        lambda _url: (client, response),
    )

    downloaded = updater_service._download_installer(
        "https://github.com/jampat000/MediaMop/releases/download/v2.1.2/MediaMopSetup.exe",
        target_version="2.1.2",
        attempt_id="attempt-123",
    )

    assert downloaded.exists()
    assert downloaded.read_bytes() == b"abcdefgh"
    assert response.closed is True
    assert client.closed is True


def test_perform_upgrade_attempt_allows_missing_checksum_only_with_explicit_override(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    attempt_id = "attempt-123"
    installer = tmp_path / "MediaMopSetup.exe"
    installer.write_bytes(b"installer")
    updater_service._persist_state(updater_service._fresh_attempt_state("2.0.8", attempt_id))
    monkeypatch.setenv("MEDIAMOP_UPDATER_ALLOW_UNVERIFIED", "true")

    class _DoneProcess:
        pid = 6789

        def wait(self, timeout: float) -> int:
            Path(updater_service._read_state()["installer_log_path"]).write_text("installer log", encoding="utf-8")
            return 0

    monkeypatch.setattr(
        updater_service,
        "fetch_release_record_by_version",
        lambda version, user_agent_version: _release_with_assets(
            version,
            {"MediaMopSetup.exe"},
        ),
    )
    monkeypatch.setattr(updater_service, "_download_installer", lambda _url, target_version, attempt_id: installer)
    monkeypatch.setattr(updater_service, "_sha256_for_path", lambda _path: "b" * 64)
    monkeypatch.setattr(updater_service, "_verify_authenticode_signature", lambda _path: (True, "not required"))
    monkeypatch.setattr(updater_service, "_launch_installer", lambda _path, installer_log_path: _DoneProcess())
    monkeypatch.setattr(
        updater_service,
        "_verify_install",
        lambda target_version: (
            True,
            {"backend_version": target_version, "packaged_version": target_version},
            f"Upgrade completed. Running version: {target_version}.",
        ),
    )

    updater_service._perform_upgrade_attempt(attempt_id)
    state = updater_service._read_state()

    assert state["phase"] == "completed"
    assert state["expected_sha256"] is None
    assert state["installer_sha256"] == "b" * 64


def test_verify_install_relaunches_tray_before_marking_upgrade_complete(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    target_version = "2.0.8"
    observed = {"tray_calls": 0, "server_calls": 0}
    diagnostics_iter = iter(
        [
            {
                "packaged_version": target_version,
                "missing_required_files": [],
                "backend_ready": False,
                "backend_version": None,
                "tray_running": False,
            },
            {
                "packaged_version": target_version,
                "missing_required_files": [],
                "backend_ready": False,
                "backend_version": None,
                "tray_running": False,
            },
            {
                "packaged_version": target_version,
                "missing_required_files": [],
                "backend_ready": True,
                "backend_version": target_version,
                "tray_running": True,
            },
        ]
    )
    clock = iter(range(1000))

    monkeypatch.setattr(updater_service, "_read_runtime_port", lambda: 8788)
    monkeypatch.setattr(
        updater_service,
        "_collect_install_diagnostics",
        lambda _target_version, *, port: next(diagnostics_iter),
    )
    monkeypatch.setattr(
        updater_service,
        "_start_packaged_tray_in_active_session",
        lambda *, open_browser=False: observed.__setitem__("tray_calls", observed["tray_calls"] + 1) or 4321,
    )
    monkeypatch.setattr(
        updater_service,
        "_start_packaged_server",
        lambda _port: observed.__setitem__("server_calls", observed["server_calls"] + 1),
    )
    monkeypatch.setattr(updater_service.time, "time", lambda: float(next(clock)))
    monkeypatch.setattr(updater_service.time, "sleep", lambda _seconds: None)

    verified, diagnostics, message = updater_service._verify_install(target_version)

    assert verified is True
    assert message == f"Upgrade completed. Running version: {target_version}."
    assert observed["tray_calls"] == 1
    assert observed["server_calls"] == 0
    assert diagnostics["restarted_tray_pid"] == 4321
    assert diagnostics["tray_relaunch_attempted"] is True


def test_verify_install_falls_back_to_server_when_tray_relaunch_is_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    target_version = "2.0.8"
    observed = {"server_calls": 0}
    diagnostics_iter = iter(
        [
            {
                "packaged_version": target_version,
                "missing_required_files": [],
                "backend_ready": False,
                "backend_version": None,
                "tray_running": False,
            },
            {
                "packaged_version": target_version,
                "missing_required_files": [],
                "backend_ready": False,
                "backend_version": None,
                "tray_running": False,
            },
            {
                "packaged_version": target_version,
                "missing_required_files": [],
                "backend_ready": True,
                "backend_version": target_version,
                "tray_running": False,
            },
        ]
    )
    clock = iter(range(1000))

    class _ServerProcess:
        pid = 5566

    monkeypatch.setattr(updater_service, "_read_runtime_port", lambda: 8788)
    monkeypatch.setattr(
        updater_service,
        "_collect_install_diagnostics",
        lambda _target_version, *, port: next(diagnostics_iter),
    )
    monkeypatch.setattr(
        updater_service,
        "_start_packaged_tray_in_active_session",
        lambda *, open_browser=False: (_ for _ in ()).throw(RuntimeError("no interactive session")),
    )
    monkeypatch.setattr(
        updater_service,
        "_start_packaged_server",
        lambda _port: observed.__setitem__("server_calls", observed["server_calls"] + 1) or _ServerProcess(),
    )
    monkeypatch.setattr(updater_service.time, "time", lambda: float(next(clock)))
    monkeypatch.setattr(updater_service.time, "sleep", lambda _seconds: None)

    verified, diagnostics, message = updater_service._verify_install(target_version)

    assert verified is True
    assert message == f"Upgrade completed. Running version: {target_version}."
    assert observed["server_calls"] == 1
    assert diagnostics["restarted_server_pid"] == 5566
    assert diagnostics["tray_restart_error"] == "no interactive session"


def test_packaged_helper_exits_after_launch_and_reconciliation_completes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    attempt_id = "attempt-123"
    installer = tmp_path / "MediaMopSetup.exe"
    installer.write_bytes(b"installer")
    updater_service._persist_state(updater_service._fresh_attempt_state("2.0.8", attempt_id))

    class _LaunchedProcess:
        pid = 6789

    with monkeypatch.context() as scoped:
        scoped.setattr(updater_service.os, "name", "nt")
        scoped.setattr(
            updater_service,
            "fetch_release_record_by_version",
            lambda version, user_agent_version: _release_with_assets(version),
        )
        scoped.setattr(updater_service, "_download_text", lambda _url: "a" * 64 + "  MediaMopSetup.exe")
        scoped.setattr(updater_service, "_download_installer", lambda _url, target_version, attempt_id: installer)
        scoped.setattr(updater_service, "_sha256_for_path", lambda _path: "a" * 64)
        scoped.setattr(updater_service, "_verify_authenticode_signature", lambda _path: (True, "not required"))
        scoped.setattr(updater_service, "_launch_installer", lambda _path, installer_log_path: _LaunchedProcess())
        scoped.setattr(updater_service.sys, "frozen", True, raising=False)

        updater_service._perform_upgrade_attempt(attempt_id)
        launch_state = updater_service._read_state()

    assert launch_state["phase"] == "installer_running"
    assert launch_state["diagnostics"]["installer_pid"] == 6789
    assert launch_state["diagnostics"]["helper_pid"] is None

    Path(launch_state["installer_log_path"]).write_text("installer log", encoding="utf-8")
    updater_service._write_state(diagnostics={"helper_pid": None})
    monkeypatch.setattr(updater_service, "_pid_is_running", lambda _pid: False)
    monkeypatch.setattr(
        updater_service,
        "_verify_install",
        lambda target_version: (
            True,
            {"backend_version": target_version, "packaged_version": target_version},
            f"Upgrade completed. Running version: {target_version}.",
        ),
    )

    updater_service._reconcile_attempt_worker(attempt_id)
    state = updater_service._read_state()

    assert state["phase"] == "completed"
    assert state["current_version_seen"] == "2.0.8"


def test_reconcile_attempt_worker_fails_when_installer_does_not_exit_in_time(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    installer = tmp_path / "MediaMopSetup-2.0.8-attempt-123.exe"
    installer.write_bytes(b"installer")
    updater_service._persist_state(
        {
            **updater_service._fresh_attempt_state("2.0.8", "attempt-123"),
            "phase": "installer_running",
            "downloaded_installer_path": str(installer),
            "diagnostics": {"helper_pid": None, "installer_pid": 6789},
        }
    )
    clock = iter([0.0, float(updater_service._INSTALLER_WAIT_TIMEOUT_SECONDS + 1)])

    monkeypatch.setattr(updater_service.time, "time", lambda: next(clock))
    monkeypatch.setattr(updater_service.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(updater_service, "_installer_process_is_running", lambda _state: True)

    updater_service._reconcile_attempt_worker("attempt-123")
    state = updater_service._read_state()

    assert state["phase"] == "failed"
    assert "reconciliation timeout elapsed" in str(state["last_error"]).lower()


def test_apply_update_persists_state_before_launching_helper(tmp_path: Path, monkeypatch) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    observed: dict[str, object] = {}

    class _Helper:
        pid = 4321

    def _launch_helper(attempt_id: str) -> _Helper:
        state = updater_service._read_state()
        observed["attempt_id"] = attempt_id
        observed["phase"] = state["phase"]
        observed["state_attempt_id"] = state["attempt_id"]
        observed["target_version"] = state["target_version"]
        return _Helper()

    with monkeypatch.context() as scoped:
        scoped.setattr(updater_service.os, "name", "nt")
        scoped.setattr(updater_service, "_load_or_create_token", lambda: "token")
        scoped.setattr(updater_service, "_launch_helper", _launch_helper)
        scoped.setattr(updater_service.uuid, "uuid4", lambda: type("Uuid", (), {"hex": "attempt-123"})())
        app = updater_service.create_updater_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            res = client.post(
                "/api/v1/apply",
                headers={"X-MediaMop-Updater-Token": "token"},
                json={"target_version": "2.0.8"},
            )

    assert res.status_code == 200
    assert observed == {
        "attempt_id": "attempt-123",
        "phase": "checking",
        "state_attempt_id": "attempt-123",
        "target_version": "2.0.8",
    }


def test_stable_or_active_attempt_exists_does_not_block_completed_target_version(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    installer = tmp_path / "MediaMopSetup-2.0.8-attempt-123.exe"
    installer.write_bytes(b"installer")
    state = {
        **updater_service._fresh_attempt_state("2.0.8", "attempt-123"),
        "phase": "installer_running",
        "downloaded_installer_path": str(installer),
        "diagnostics": {"helper_pid": None, "installer_pid": 6789},
    }
    monkeypatch.setattr(updater_service, "_installer_process_is_running", lambda _state: False)
    monkeypatch.setattr(
        updater_service,
        "_state_matches_installed_target",
        lambda target_version: (
            True,
            {"backend_version": target_version, "packaged_version": target_version},
        ),
    )

    assert updater_service._stable_or_active_attempt_exists(state) is False


def test_stable_or_active_attempt_exists_does_not_block_when_running_version_exceeds_target(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    installer = tmp_path / "MediaMopSetup-2.1.0-attempt-123.exe"
    installer.write_bytes(b"installer")
    state = {
        **updater_service._fresh_attempt_state("2.1.0", "attempt-123"),
        "phase": "installer_running",
        "downloaded_installer_path": str(installer),
        "diagnostics": {"helper_pid": None, "installer_pid": 6789},
    }
    monkeypatch.setattr(updater_service, "_installer_process_is_running", lambda _state: False)
    monkeypatch.setattr(updater_service, "_state_matches_installed_target", lambda _target_version: (False, {}))
    monkeypatch.setattr(
        updater_service,
        "_state_running_version_exceeds_target",
        lambda target_version: (True, {"backend_version": "2.1.2"}, "2.1.2"),
    )

    assert updater_service._stable_or_active_attempt_exists(state) is False


def test_maybe_reconcile_pending_attempt_marks_stale_attempt_failed(tmp_path: Path, monkeypatch) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    state_path = updater_service._state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "phase": "downloading",
                "attempt_id": "attempt-123",
                "target_version": "2.0.8",
                "last_started_at": "2026-05-06T00:00:00+00:00",
                "last_updated_at": "2026-05-06T00:00:00+00:00",
                "diagnostics": {"helper_pid": None, "installer_pid": None},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(updater_service, "_state_age_seconds", lambda _state: updater_service._STALE_ATTEMPT_SECONDS + 5)

    updater_service._maybe_reconcile_pending_attempt()
    state = updater_service._read_state()

    assert state["phase"] == "failed"
    assert "stalled during downloading" in str(state["last_error"]).lower()


def test_maybe_reconcile_pending_attempt_marks_already_running_target_completed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    installer = tmp_path / "MediaMopSetup-2.0.8-attempt-123.exe"
    installer.write_bytes(b"installer")
    updater_service._persist_state(
        {
            **updater_service._fresh_attempt_state("2.0.8", "attempt-123"),
            "phase": "installer_running",
            "downloaded_installer_path": str(installer),
            "diagnostics": {"helper_pid": None, "installer_pid": 6789},
        }
    )
    Path(updater_service._read_state()["installer_log_path"]).write_text("installer log", encoding="utf-8")
    monkeypatch.setattr(updater_service, "_installer_process_is_running", lambda _state: False)
    monkeypatch.setattr(
        updater_service,
        "_state_matches_installed_target",
        lambda target_version: (
            True,
            {
                "backend_version": target_version,
                "packaged_version": target_version,
                "missing_required_files": [],
            },
        ),
    )

    updater_service._maybe_reconcile_pending_attempt()
    state = updater_service._read_state()

    assert state["phase"] == "completed"
    assert state["current_version_seen"] == "2.0.8"
    assert state["diagnostics"]["reconciled_after_restart"] is True


def test_maybe_reconcile_pending_attempt_reconciles_unverifiable_installer_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    installer = tmp_path / "MediaMopSetup-2.0.8-attempt-123.exe"
    installer.write_bytes(b"installer")
    updater_service._persist_state(
        {
            **updater_service._fresh_attempt_state("2.0.8", "attempt-123"),
            "phase": "installer_running",
            "downloaded_installer_path": str(installer),
            "diagnostics": {"helper_pid": None, "installer_pid": 6789},
        }
    )
    Path(updater_service._read_state()["installer_log_path"]).write_text("installer log", encoding="utf-8")
    monkeypatch.setattr(updater_service, "_read_process_snapshot", lambda _pid: None)
    monkeypatch.setattr(
        updater_service,
        "_state_matches_installed_target",
        lambda target_version: (
            True,
            {
                "backend_version": target_version,
                "packaged_version": target_version,
                "missing_required_files": [],
            },
        ),
    )

    updater_service._maybe_reconcile_pending_attempt()
    state = updater_service._read_state()

    assert state["phase"] == "completed"
    assert "could not prove" in str(state["diagnostics"]["stale_reason"]).lower()


def test_maybe_reconcile_pending_attempt_recovers_legacy_active_state_without_attempt_id(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    updater_service._persist_state(
        {
            "phase": "installer_running",
            "message": "MediaMop 2.1.0 installer is running.",
            "target_version": "2.1.0",
            "last_started_at": "2026-05-07T04:39:51+00:00",
            "installer_log_path": str(tmp_path / "installer-latest.log"),
        }
    )
    monkeypatch.setattr(
        updater_service,
        "_state_matches_installed_target",
        lambda target_version: (
            True,
            {
                "backend_version": target_version,
                "packaged_version": target_version,
                "missing_required_files": [],
            },
        ),
    )

    updater_service._maybe_reconcile_pending_attempt()
    state = updater_service._read_state()

    assert state["phase"] == "completed"
    assert state["current_version_seen"] == "2.1.0"
    assert state["diagnostics"]["reconciled_after_restart"] is True


def test_maybe_reconcile_pending_attempt_fails_obsolete_legacy_state_without_attempt_id(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    updater_service._persist_state(
        {
            "phase": "installer_running",
            "message": "MediaMop 2.1.0 installer is running.",
            "target_version": "2.1.0",
            "last_started_at": "2026-05-07T04:39:51+00:00",
            "installer_log_path": str(tmp_path / "installer-latest.log"),
        }
    )
    monkeypatch.setattr(updater_service, "_state_matches_installed_target", lambda _target_version: (False, {}))
    monkeypatch.setattr(
        updater_service,
        "_state_running_version_exceeds_target",
        lambda target_version: (
            True,
            {"backend_version": "2.1.2", "packaged_version": "2.1.2"},
            "2.1.2",
        ),
    )

    updater_service._maybe_reconcile_pending_attempt()
    state = updater_service._read_state()

    assert state["phase"] == "failed"
    assert state["current_version_seen"] == "2.1.2"
    assert "still targeted 2.1.0" in str(state["last_error"]).lower()
    assert state["diagnostics"]["reconciled_from_phase"] == "installer_running"


def test_status_endpoint_reports_reconciled_legacy_state_as_non_active(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    updater_service._persist_state(
        {
            "phase": "installer_running",
            "message": "MediaMop 2.1.0 installer is running.",
            "target_version": "2.1.0",
            "last_started_at": "2026-05-07T04:39:51+00:00",
            "installer_log_path": str(tmp_path / "installer-latest.log"),
        }
    )
    monkeypatch.setattr(
        updater_service,
        "_state_matches_installed_target",
        lambda target_version: (
            True,
            {
                "backend_version": target_version,
                "packaged_version": target_version,
                "missing_required_files": [],
            },
        ),
    )
    with monkeypatch.context() as scoped:
        scoped.setattr(updater_service.os, "name", "nt")
        scoped.setattr(updater_service, "_load_or_create_token", lambda: "token")
        app = updater_service.create_updater_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            res = client.get(
                "/api/v1/status",
                headers={"X-MediaMop-Updater-Token": "token"},
            )

    assert res.status_code == 200
    body = res.json()
    assert body["phase"] == "completed"
    assert body["raw_phase"] == "installer_running"
    assert body["is_active"] is False
    assert body["blocks_new_update"] is False
    assert body["is_stale"] is True
    assert "could not prove" in body["stale_reason"].lower()


@pytest.mark.parametrize("phase", ["installer_running", "restarting", "verifying_install"])
def test_maybe_reconcile_pending_attempt_resumes_verification_for_recoverable_phases(
    tmp_path: Path,
    monkeypatch,
    phase: str,
) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    updater_service._persist_state(
        {
            **updater_service._fresh_attempt_state("2.0.8", "attempt-123"),
            "phase": phase,
            "message": "waiting",
            "diagnostics": {"helper_pid": None, "installer_pid": None},
        }
    )
    Path(updater_service._read_state()["installer_log_path"]).write_text("installer log", encoding="utf-8")

    class _ImmediateThread:
        def __init__(self, *, target, args, daemon, name) -> None:
            self._target = target
            self._args = args

        def start(self) -> None:
            self._target(*self._args)

    monkeypatch.setattr(updater_service, "_state_age_seconds", lambda _state: 5)
    monkeypatch.setattr(updater_service, "_pid_is_running", lambda _pid: False)
    monkeypatch.setattr(updater_service.threading, "Thread", _ImmediateThread)
    monkeypatch.setattr(
        updater_service,
        "_verify_install",
        lambda target_version: (
            True,
            {"backend_version": target_version, "packaged_version": target_version},
            f"Upgrade completed. Running version: {target_version}.",
        ),
    )

    updater_service._maybe_reconcile_pending_attempt()
    state = updater_service._read_state()

    assert state["phase"] == "completed"
    assert state["diagnostics"]["reconciled_after_restart"] is True


@pytest.mark.parametrize("phase", ["installer_running", "restarting", "verifying_install"])
def test_maybe_reconcile_pending_attempt_fails_stale_recoverable_phases(
    tmp_path: Path,
    monkeypatch,
    phase: str,
) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    updater_service._persist_state(
        {
            **updater_service._fresh_attempt_state("2.0.8", "attempt-123"),
            "phase": phase,
            "message": "waiting",
            "diagnostics": {"helper_pid": None, "installer_pid": None},
        }
    )
    monkeypatch.setattr(
        updater_service,
        "_state_age_seconds",
        lambda _state: updater_service._STALE_ATTEMPT_SECONDS + 5,
    )
    monkeypatch.setattr(updater_service, "_pid_is_running", lambda _pid: False)

    updater_service._maybe_reconcile_pending_attempt()
    state = updater_service._read_state()

    assert state["phase"] == "failed"
    assert f"stalled during {phase}" in str(state["last_error"]).lower()


def test_parse_sha256_manifest_prefers_installer_line() -> None:
    manifest = "\n".join(
        [
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb  something-else.exe",
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa  MediaMopSetup.exe",
        ]
    )

    assert updater_service._parse_sha256_manifest(manifest) == "a" * 64


def test_validated_asset_download_url_rejects_wrong_tag() -> None:
    try:
        updater_service._validated_asset_download_url(
            "https://github.com/jampat000/MediaMop/releases/download/v2.0.7/MediaMopSetup.exe",
            version="2.0.8",
            asset_name="MediaMopSetup.exe",
        )
    except ValueError as exc:
        assert "did not match" in str(exc)
    else:
        raise AssertionError("expected ValueError")


@pytest.mark.parametrize(
    ("url", "asset_name", "expected"),
    [
        (
            "https://github.com/other/MediaMop/releases/download/v2.0.8/MediaMopSetup.exe",
            "MediaMopSetup.exe",
            "did not match",
        ),
        (
            "https://github.com/jampat000/OtherRepo/releases/download/v2.0.8/MediaMopSetup.exe",
            "MediaMopSetup.exe",
            "did not match",
        ),
        (
            "https://github.com/jampat000/MediaMop/releases/download/v2.0.8/OtherSetup.exe",
            "MediaMopSetup.exe",
            "did not match",
        ),
    ],
)
def test_validated_asset_download_url_rejects_wrong_owner_repo_or_asset_name(
    url: str,
    asset_name: str,
    expected: str,
) -> None:
    with pytest.raises(ValueError, match=expected):
        updater_service._validated_asset_download_url(
            url,
            version="2.0.8",
            asset_name=asset_name,
        )


def test_validated_redirect_target_rejects_untrusted_host() -> None:
    with pytest.raises(ValueError, match="untrusted host"):
        updater_service._validated_redirect_target(
            "https://github.com/jampat000/MediaMop/releases/download/v2.0.8/MediaMopSetup.exe",
            "https://example.com/MediaMopSetup.exe",
        )


def test_verify_authenticode_signature_is_optional_by_default(tmp_path: Path, monkeypatch) -> None:
    installer = tmp_path / "MediaMopSetup.exe"
    installer.write_bytes(b"installer")
    monkeypatch.delenv("MEDIAMOP_UPDATER_REQUIRE_AUTHENTICODE", raising=False)

    ok, detail = updater_service._verify_authenticode_signature(installer)

    assert ok is True
    assert detail == "Authenticode verification not required."


def test_verify_authenticode_signature_requires_valid_signature_when_enabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    installer = tmp_path / "MediaMopSetup.exe"
    installer.write_bytes(b"installer")
    monkeypatch.setenv("MEDIAMOP_UPDATER_REQUIRE_AUTHENTICODE", "true")

    def _fake_run(cmd, **kwargs):  # noqa: ANN001
        return type(
            "Result",
            (),
            {
                "returncode": 0,
                "stdout": '{"Status":"UnknownError","StatusMessage":"bad","Signer":""}',
                "stderr": "",
            },
        )()

    monkeypatch.setattr(updater_service.subprocess, "run", _fake_run)

    ok, detail = updater_service._verify_authenticode_signature(installer)

    assert ok is False
    assert "Authenticode signature verification failed" in detail


def test_harden_token_acl_windows_uses_icacls(tmp_path: Path, monkeypatch) -> None:
    token_path = tmp_path / "updater.secret"
    token_path.write_text("token", encoding="utf-8")
    observed: dict[str, object] = {}

    def _fake_run(cmd, **kwargs):  # noqa: ANN001
        observed["cmd"] = cmd
        return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(updater_service.subprocess, "run", _fake_run)

    updater_service._harden_token_acl_windows(token_path)

    assert observed["cmd"] == [
        "icacls",
        str(token_path),
        "/inheritance:r",
        "/grant:r",
        "SYSTEM:R",
        "/grant:r",
        "Administrators:R",
        "/grant:r",
        "INTERACTIVE:R",
    ]


def test_read_state_surfaces_state_corruption(tmp_path: Path, monkeypatch) -> None:
    _configure_runtime_home(tmp_path, monkeypatch)
    state_path = updater_service._state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text("{bad json", encoding="utf-8")

    state = updater_service._read_state()

    assert state["phase"] == "state_corrupt"
    assert "Could not parse updater state file" in str(state["last_error"])
