"""Unit: ``refiner_runtime_visibility_from_settings`` maps settings to the visibility DTO."""

from __future__ import annotations

from dataclasses import replace

import pytest

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.runtime_visibility import refiner_runtime_visibility_from_settings


@pytest.fixture
def base_settings(monkeypatch: pytest.MonkeyPatch) -> MediaMopSettings:
    monkeypatch.setenv("MEDIAMOP_REFINER_WORKER_COUNT", "1")
    monkeypatch.setenv("MEDIAMOP_REFINER_RADARR_CLEANUP_DRIVE_SCHEDULE_ENABLED", "0")
    monkeypatch.setenv("MEDIAMOP_REFINER_SONARR_CLEANUP_DRIVE_SCHEDULE_ENABLED", "0")
    return MediaMopSettings.load()


def test_worker_count_zero_disabled_summary(base_settings: MediaMopSettings) -> None:
    s = replace(base_settings, refiner_worker_count=0)
    out = refiner_runtime_visibility_from_settings(s)
    assert out.refiner_worker_count == 0
    assert out.in_process_workers_disabled is True
    assert out.in_process_workers_enabled is False
    assert "disabled" in out.worker_mode_summary.lower()
    assert "0" in out.worker_mode_summary


def test_worker_count_one_default_summary(base_settings: MediaMopSettings) -> None:
    s = replace(base_settings, refiner_worker_count=1)
    out = refiner_runtime_visibility_from_settings(s)
    assert out.refiner_worker_count == 1
    assert out.in_process_workers_disabled is False
    assert out.in_process_workers_enabled is True
    assert "single" in out.worker_mode_summary.lower() or "default" in out.worker_mode_summary.lower()
    assert "guarded" not in out.worker_mode_summary.lower()


def test_worker_count_multi_guarded_wording(base_settings: MediaMopSettings) -> None:
    s = replace(base_settings, refiner_worker_count=3)
    out = refiner_runtime_visibility_from_settings(s)
    assert out.refiner_worker_count == 3
    assert "guarded" in out.worker_mode_summary.lower()
    assert "not the normal" in out.worker_mode_summary.lower() or "recommended" in out.worker_mode_summary.lower()


def test_radarr_and_sonarr_schedules_independent(base_settings: MediaMopSettings) -> None:
    s = replace(
        base_settings,
        refiner_radarr_cleanup_drive_schedule_enabled=True,
        refiner_radarr_cleanup_drive_schedule_interval_seconds=7200,
        refiner_sonarr_cleanup_drive_schedule_enabled=False,
        refiner_sonarr_cleanup_drive_schedule_interval_seconds=3600,
    )
    out = refiner_runtime_visibility_from_settings(s)
    assert out.refiner_radarr_cleanup_drive_schedule_enabled is True
    assert out.refiner_radarr_cleanup_drive_schedule_interval_seconds == 7200
    assert out.refiner_sonarr_cleanup_drive_schedule_enabled is False
    assert out.refiner_sonarr_cleanup_drive_schedule_interval_seconds == 3600


def test_visibility_note_present(base_settings: MediaMopSettings) -> None:
    out = refiner_runtime_visibility_from_settings(base_settings)
    assert "settings" in out.visibility_note.lower()
    assert "liveness" in out.visibility_note.lower() or "healthy" in out.visibility_note.lower()
