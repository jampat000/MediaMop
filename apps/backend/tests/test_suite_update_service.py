from __future__ import annotations

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
    assert status.docker_update_command == "docker pull ghcr.io/jampat000/mediamop:2.0.8 && docker compose up -d"
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
