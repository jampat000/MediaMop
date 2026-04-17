"""Test-suite helpers for HTTP integration tests that spin ``create_app`` with ``MEDIAMOP_HOME``.

Disabling in-process workers and periodic enqueue schedules prevents background tasks in other
product lanes from writing to the same SQLite file used by the test, which would otherwise create
implicit cross-lane coupling (ADR-0007 session semantics).

This module is **tests-only**; production code must not import it.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def integration_test_set_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home_segment: str) -> Path:
    home = tmp_path / home_segment
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MEDIAMOP_HOME", str(home))
    return home


def integration_test_quiesce_in_process_workers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_FETCHER_WORKER_COUNT", "0")
    monkeypatch.setenv("MEDIAMOP_REFINER_WORKER_COUNT", "0")
    monkeypatch.setenv("MEDIAMOP_PRUNER_WORKER_COUNT", "0")
    monkeypatch.setenv("MEDIAMOP_SUBBER_WORKER_COUNT", "0")


def integration_test_quiesce_periodic_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    """Turn off :class:`mediamop.core.config.MediaMopSettings` periodic enqueue toggles for the suite DB."""

    monkeypatch.setenv("MEDIAMOP_REFINER_SUPPLIED_PAYLOAD_EVALUATION_SCHEDULE_ENABLED", "0")
    monkeypatch.setenv("MEDIAMOP_REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_SCHEDULE_ENABLED", "0")
    monkeypatch.setenv("MEDIAMOP_REFINER_WORK_TEMP_STALE_SWEEP_MOVIE_SCHEDULE_ENABLED", "0")
    monkeypatch.setenv("MEDIAMOP_REFINER_WORK_TEMP_STALE_SWEEP_TV_SCHEDULE_ENABLED", "0")
    monkeypatch.setenv("MEDIAMOP_REFINER_MOVIE_FAILURE_CLEANUP_SCHEDULE_ENABLED", "0")
    monkeypatch.setenv("MEDIAMOP_REFINER_TV_FAILURE_CLEANUP_SCHEDULE_ENABLED", "0")
    monkeypatch.setenv("MEDIAMOP_FAILED_IMPORT_RADARR_CLEANUP_DRIVE_SCHEDULE_ENABLED", "0")
    monkeypatch.setenv("MEDIAMOP_FAILED_IMPORT_SONARR_CLEANUP_DRIVE_SCHEDULE_ENABLED", "0")
    monkeypatch.setenv("MEDIAMOP_FETCHER_SONARR_MISSING_SEARCH_SCHEDULE_ENABLED", "0")
    monkeypatch.setenv("MEDIAMOP_FETCHER_SONARR_UPGRADE_SEARCH_SCHEDULE_ENABLED", "0")
    monkeypatch.setenv("MEDIAMOP_FETCHER_RADARR_MISSING_SEARCH_SCHEDULE_ENABLED", "0")
    monkeypatch.setenv("MEDIAMOP_FETCHER_RADARR_UPGRADE_SEARCH_SCHEDULE_ENABLED", "0")
