from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mediamop.platform.suite_settings import update_service
from mediamop.platform.suite_settings.release_catalog import (
    GitHubReleaseAsset,
    GitHubReleaseRecord,
)


def _release_record(version: str = "2.0.8") -> GitHubReleaseRecord:
    return GitHubReleaseRecord(
        tag_name=f"v{version}",
        version=version,
        release_name=f"MediaMop {version}",
        html_url="https://example.com/release",
        published_at=datetime(2026, 5, 7, tzinfo=UTC),
        draft=False,
        prerelease=False,
        assets=(
            GitHubReleaseAsset(
                name="MediaMopSetup.exe",
                api_url="https://api.github.com/repos/jampat000/MediaMop/releases/assets/1",
                browser_download_url=f"https://github.com/jampat000/MediaMop/releases/download/v{version}/MediaMopSetup.exe",
                size_bytes=123456789,
                content_type="application/octet-stream",
            ),
        ),
    )


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

        @staticmethod
        def json() -> dict[str, object]:
            return {
                "phase": "installer_running",
                "message": "Installer is running. MediaMop may temporarily disconnect.",
                "target_version": "2.0.8",
            }

    def _fake_get(url: str, *, headers: dict[str, str] | None = None, timeout: float | None = None) -> _Resp:
        observed["url"] = url
        observed["headers"] = headers
        observed["timeout"] = timeout
        return _Resp()

    with monkeypatch.context() as scoped:
        scoped.setattr(
            "mediamop.platform.suite_settings.update_service._updater_headers",
            lambda _settings=None: {"X-MediaMop-Updater-Token": "token-value"},
        )
        scoped.setattr("mediamop.platform.suite_settings.update_service.httpx.get", _fake_get)

        ready, summary, progress = update_service._fetch_windows_updater_progress()

        assert ready is True
        assert summary == "Remote in-app upgrade is ready on this Windows install."
        assert progress is not None
        assert progress.phase == "installer_running"
        assert progress.is_active is True
        assert progress.blocks_new_update is True
        assert observed["url"] == f"{update_service._updater_base_url()}/api/v1/status"
        assert observed["headers"] == {"X-MediaMop-Updater-Token": "token-value"}
        assert observed["timeout"] == 3.0


def test_windows_updater_service_ready_false_on_unauthorized(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Resp:
        status_code = 401

        @staticmethod
        def json() -> dict[str, object]:
            return {}

    with monkeypatch.context() as scoped:
        scoped.setattr(
            "mediamop.platform.suite_settings.update_service._updater_headers",
            lambda _settings=None: {"X-MediaMop-Updater-Token": "bad-token"},
        )
        scoped.setattr("mediamop.platform.suite_settings.update_service.httpx.get", lambda *_args, **_kwargs: _Resp())

        ready, summary, progress = update_service._fetch_windows_updater_progress()

        assert ready is False
        assert "token did not match" in summary.lower()
        assert progress is None


def test_start_windows_updater_service_apply_posts_target_version_only(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: dict[str, object] = {}

    class _Resp:
        status_code = 200

        @staticmethod
        def json() -> dict[str, object]:
            return {
                "accepted": True,
                "attempt_id": "attempt-123",
                "message": "Upgrade request accepted. MediaMop is checking release metadata.",
            }

    def _fake_post(url: str, *, headers: dict[str, str] | None = None, json=None, timeout: float | None = None) -> _Resp:  # noqa: ANN001
        observed["url"] = url
        observed["headers"] = headers
        observed["json"] = json
        observed["timeout"] = timeout
        return _Resp()

    with monkeypatch.context() as scoped:
        scoped.setattr(
            "mediamop.platform.suite_settings.update_service._updater_headers",
            lambda _settings=None: {"X-MediaMop-Updater-Token": "token-value"},
        )
        scoped.setattr("mediamop.platform.suite_settings.update_service.httpx.post", _fake_post)

        started, message, attempt_id = update_service._start_windows_updater_service_apply(
            object(),  # type: ignore[arg-type]
            target_version="v2.0.8",
        )

        assert started is True
        assert attempt_id == "attempt-123"
        assert message == "Upgrade request accepted. MediaMop is checking release metadata."
        assert observed["url"] == f"{update_service._updater_base_url()}/api/v1/apply"
        assert observed["json"] == {"target_version": "2.0.8"}


def test_build_suite_update_status_includes_upgrade_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "mediamop.platform.suite_settings.update_service.fetch_latest_release_record",
        lambda **_kwargs: _release_record("2.0.8"),
    )
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service.__version__", "2.0.7")
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service._detect_install_type", lambda: "windows")
    monkeypatch.setattr(
        "mediamop.platform.suite_settings.update_service._fetch_windows_updater_progress",
        lambda _settings=None: (
            True,
            "Remote in-app upgrade is ready on this Windows install.",
            update_service._coerce_upgrade_progress(
                {
                    "phase": "verifying_install",
                    "message": "MediaMop is reconnecting and verifying the installed version.",
                    "attempt_id": "attempt-123",
                    "target_version": "2.0.8",
                    "installer_log_path": "C:/ProgramData/MediaMop/upgrades/installer-attempt-123.log",
                }
            ),
        ),
    )

    status = update_service.build_suite_update_status()

    assert status.status == "update_available"
    assert status.latest_version == "2.0.8"
    assert status.upgrade is not None
    assert status.upgrade.phase == "verifying_install"
    assert status.upgrade.attempt_id == "attempt-123"
    assert status.upgrade.is_active is True


def test_coerce_upgrade_progress_hides_idle_state() -> None:
    assert (
        update_service._coerce_upgrade_progress(
            {
                "phase": "idle",
                "message": "Updater ready.",
            }
        )
        is None
    )


def test_coerce_upgrade_progress_marks_stale_completed_state_non_blocking() -> None:
    progress = update_service._coerce_upgrade_progress(
        {
            "phase": "completed",
            "raw_phase": "installer_running",
            "message": "Upgrade completed. Running version: 2.1.0.",
            "target_version": "2.1.0",
            "is_active": False,
            "blocks_new_update": False,
            "stale_reason": "Persisted updater state could not prove the original installer process was still active.",
        }
    )

    assert progress is not None
    assert progress.phase == "completed"
    assert progress.raw_phase == "installer_running"
    assert progress.is_active is False
    assert progress.is_stale is True
    assert progress.blocks_new_update is False


def test_build_suite_update_status_keeps_newer_release_available_when_old_state_is_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "mediamop.platform.suite_settings.update_service.fetch_latest_release_record",
        lambda **_kwargs: _release_record("2.1.2"),
    )
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service.__version__", "2.1.0")
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service._detect_install_type", lambda: "windows")
    monkeypatch.setattr(
        "mediamop.platform.suite_settings.update_service._fetch_windows_updater_progress",
        lambda _settings=None: (
            True,
            "Remote in-app upgrade is ready on this Windows install.",
            update_service._coerce_upgrade_progress(
                {
                    "phase": "completed",
                    "raw_phase": "installer_running",
                    "message": "Upgrade completed. Running version: 2.1.0.",
                    "target_version": "2.1.0",
                    "current_version_seen": "2.1.0",
                    "is_active": False,
                    "blocks_new_update": False,
                    "stale_reason": "Persisted updater state could not prove the original installer process was still active.",
                }
            ),
        ),
    )

    status = update_service.build_suite_update_status()

    assert status.status == "update_available"
    assert status.latest_version == "2.1.2"
    assert status.upgrade is not None
    assert status.upgrade.is_active is False
    assert status.upgrade.blocks_new_update is False


def test_start_suite_update_now_returns_attempt_id(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = type("Settings", (), {"mediamop_home": str(tmp_path)})()
    monkeypatch.setenv("MEDIAMOP_RUNTIME", "windows")
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service.__version__", "2.0.7")
    monkeypatch.setattr(
        "mediamop.platform.suite_settings.update_service.fetch_latest_release_record",
        lambda **_kwargs: _release_record("2.0.8"),
    )
    monkeypatch.setattr(
        "mediamop.platform.suite_settings.update_service._start_windows_updater_service_apply",
        lambda _settings, target_version: (
            True,
            "Upgrade request accepted. MediaMop is checking release metadata.",
            "attempt-123",
        ),
    )

    out = update_service.start_suite_update_now(settings)  # type: ignore[arg-type]

    assert out.status == "started"
    assert out.attempt_id == "attempt-123"
    assert out.target_version == "2.0.8"
    assert out.log_path == str(tmp_path / "upgrades" / "updater-service.log")


def test_build_suite_update_diagnostics_reports_installed_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    install_root = tmp_path / "install"
    runtime_home = tmp_path / "runtime"
    internal = install_root / "_internal"
    internal.mkdir(parents=True)
    (internal / "mediamop_backend-2.0.8.dist-info").mkdir()
    for relative in (
        "MediaMop.exe",
        "MediaMopServer.exe",
        "MediaMopUpdater.exe",
        "MediaMopUpdaterService.exe",
        "MediaMopUpdaterService.xml",
        "_internal/web-dist/index.html",
    ):
        path = install_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")

    monkeypatch.setattr("mediamop.platform.suite_settings.update_service._install_root", lambda: install_root)
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service._runtime_home", lambda _settings=None: runtime_home)
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service._updater_token_paths", lambda _settings=None: [])
    monkeypatch.setattr(
        "mediamop.platform.suite_settings.update_service.build_suite_update_status",
        lambda _settings=None: type(
            "Status",
            (),
            {
                "current_version": "2.0.7",
                "latest_version": "2.0.8",
                "install_type": "windows",
                "in_app_upgrade_supported": True,
                "upgrade": None,
            },
        )(),
    )
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service._list_windows_processes", lambda: [])
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service._windows_file_version", lambda _path: None)

    diagnostics = update_service.build_suite_update_diagnostics()

    assert diagnostics.install_root == str(install_root)
    assert diagnostics.runtime_home == str(runtime_home)
    assert len(diagnostics.installed_files) == 6
    assert diagnostics.installed_files[1]["packaged_version"] == "2.0.8"


def test_build_suite_update_diagnostics_never_exposes_updater_token_value(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    install_root = tmp_path / "install"
    runtime_home = tmp_path / "runtime"
    token_path = runtime_home / "updater.secret"
    secret_value = "super-secret-updater-token-value"
    install_root.mkdir(parents=True)
    runtime_home.mkdir(parents=True)
    token_path.write_text(secret_value, encoding="utf-8")

    monkeypatch.setattr("mediamop.platform.suite_settings.update_service._install_root", lambda: install_root)
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service._runtime_home", lambda _settings=None: runtime_home)
    monkeypatch.setattr(
        "mediamop.platform.suite_settings.update_service._updater_token_paths",
        lambda _settings=None: [token_path],
    )
    monkeypatch.setattr(
        "mediamop.platform.suite_settings.update_service.build_suite_update_status",
        lambda _settings=None: type(
            "Status",
            (),
            {
                "current_version": "2.0.7",
                "latest_version": "2.0.8",
                "install_type": "windows",
                "in_app_upgrade_supported": True,
                "upgrade": None,
            },
        )(),
    )
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service._list_windows_processes", lambda: [])
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service._windows_file_version", lambda _path: None)

    diagnostics = update_service.build_suite_update_diagnostics()
    payload = diagnostics.model_dump()

    assert diagnostics.updater_token_path_present is True
    assert secret_value not in str(payload)
