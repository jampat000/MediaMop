from __future__ import annotations

import json
from datetime import UTC, datetime

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


def test_build_suite_update_status_returns_update_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "mediamop.platform.suite_settings.update_service.fetch_latest_release_record",
        lambda **_kwargs: _release_record("2.0.8"),
    )
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service.__version__", "2.0.7")
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service._detect_install_type", lambda: "windows")

    status = update_service.build_suite_update_status()

    assert status.status == "update_available"
    assert status.current_version == "2.0.7"
    assert status.latest_version == "2.0.8"
    assert status.install_type == "windows"
    assert status.in_app_upgrade_supported is True


def test_build_suite_update_status_returns_up_to_date(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "mediamop.platform.suite_settings.update_service.fetch_latest_release_record",
        lambda **_kwargs: _release_record("2.1.4"),
    )
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service.__version__", "2.1.4")
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service._detect_install_type", lambda: "windows")

    status = update_service.build_suite_update_status()

    assert status.status == "up_to_date"
    assert status.latest_version == "2.1.4"


def test_build_suite_update_status_windows_shows_velopack_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "mediamop.platform.suite_settings.update_service.fetch_latest_release_record",
        lambda **_kwargs: _release_record("2.0.8"),
    )
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service.__version__", "2.0.7")
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service._detect_install_type", lambda: "windows")

    status = update_service.build_suite_update_status()

    assert status.in_app_upgrade_supported is True
    assert status.in_app_upgrade_summary == "Updates are managed by the MediaMop desktop app via Velopack."


def test_build_suite_update_status_docker_includes_update_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "mediamop.platform.suite_settings.update_service.fetch_latest_release_record",
        lambda **_kwargs: _release_record("2.0.8"),
    )
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service.__version__", "2.0.7")
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service._detect_install_type", lambda: "docker")

    status = update_service.build_suite_update_status()

    assert status.status == "update_available"
    assert status.install_type == "docker"
    # Not `docker pull <image>:<tag>`: that tag does not exist (images publish as `v2.0.8`)
    # and the documented compose file pins `:latest`, so `compose up -d` would ignore it.
    assert status.docker_update_command == "docker compose pull && docker compose up -d"
    assert status.in_app_upgrade_supported is False
    assert status.in_app_upgrade_summary is None


def test_build_suite_update_status_source_has_no_upgrade_support(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "mediamop.platform.suite_settings.update_service.fetch_latest_release_record",
        lambda **_kwargs: _release_record("2.0.8"),
    )
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service.__version__", "2.0.7")
    monkeypatch.setattr("mediamop.platform.suite_settings.update_service._detect_install_type", lambda: "source")

    status = update_service.build_suite_update_status()

    assert status.install_type == "source"
    assert status.in_app_upgrade_supported is False


def _settings_for(tmp_path: object) -> object:
    """A settings object carrying only what the update-settings helpers read."""

    class _Stub:
        mediamop_home = str(tmp_path)

    return _Stub()


def test_no_settings_file_is_the_shipped_default(tmp_path: object) -> None:
    got = update_service.get_update_settings(_settings_for(tmp_path))

    assert got.mode == "Auto"
    assert got.check_on_startup is True
    assert got.check_interval_minutes == 60


def test_a_saved_choice_round_trips(tmp_path: object) -> None:
    settings = _settings_for(tmp_path)

    update_service.put_update_settings(settings, "DownloadOnly", False, 240)

    got = update_service.get_update_settings(settings)
    assert got.mode == "DownloadOnly"
    assert got.check_on_startup is False
    assert got.check_interval_minutes == 240


def test_a_truncated_file_falls_back_to_notify_only_not_to_auto(tmp_path: object) -> None:
    """The operator chose something. Auto is the one guess that can act against it."""

    settings = _settings_for(tmp_path)
    update_service.put_update_settings(settings, "NotifyOnly", True, 60)
    path = tmp_path / "update-settings.json"  # type: ignore[operator]
    path.write_text('{"mode": "Notify', encoding="utf-8")

    got = update_service.get_update_settings(settings)

    assert got.mode == "NotifyOnly"


def test_an_unknown_mode_is_rejected_rather_than_passed_through(tmp_path: object) -> None:
    """`mode` is a plain string on the wire, so a junk value must not reach the tray."""

    settings = _settings_for(tmp_path)
    path = tmp_path / "update-settings.json"  # type: ignore[operator]
    path.write_text('{"mode": "InstallEverythingNow"}', encoding="utf-8")

    assert update_service.get_update_settings(settings).mode == "NotifyOnly"


def test_the_settings_file_is_replaced_whole(tmp_path: object) -> None:
    """The write is a rename, so it leaves the payload exact and no scratch file behind."""

    settings = _settings_for(tmp_path)
    update_service.put_update_settings(settings, "DownloadOnly", True, 10080)
    update_service.put_update_settings(settings, "Auto", True, 1)

    path = tmp_path / "update-settings.json"  # type: ignore[operator]
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "mode": "Auto",
        "checkOnStartup": True,
        "checkIntervalMinutes": 1,
    }
    assert not list(path.parent.glob("*.tmp"))
