"""Unit tests for :func:`~mediamop.modules.fetcher.automation_summary_service.build_fetcher_failed_import_automation_summary`."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from sqlalchemy import delete

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.fetcher.automation_summary_service import (
    build_fetcher_failed_import_automation_summary,
)
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.fetcher.radarr_failed_import_cleanup_job import (
    RADARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY,
    FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE,
)

import mediamop.modules.refiner.jobs_model  # noqa: F401


def _session():
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    return fac()


def test_schedule_off_no_secondary_caveat() -> None:
    base = MediaMopSettings.load()
    s = replace(
        base,
        failed_import_radarr_cleanup_drive_schedule_enabled=False,
        failed_import_sonarr_cleanup_drive_schedule_enabled=False,
        refiner_worker_count=1,
    )
    with _session() as db:
        db.execute(delete(RefinerJob).where(RefinerJob.dedupe_key == RADARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY))
        db.commit()
        out = build_fetcher_failed_import_automation_summary(db, s)
    assert "off" in out.movies.saved_schedule_primary.lower()
    assert out.movies.saved_schedule_secondary is None


def test_schedule_on_interval_and_caveat() -> None:
    base = MediaMopSettings.load()
    s = replace(
        base,
        failed_import_radarr_cleanup_drive_schedule_enabled=True,
        failed_import_radarr_cleanup_drive_schedule_interval_seconds=3600,
        refiner_worker_count=1,
    )
    with _session() as db:
        db.execute(delete(RefinerJob).where(RefinerJob.dedupe_key == RADARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY))
        db.commit()
        out = build_fetcher_failed_import_automation_summary(db, s)
    assert "on" in out.movies.saved_schedule_primary.lower()
    assert "hour" in out.movies.saved_schedule_primary.lower()
    assert out.movies.saved_schedule_secondary is not None
    assert "interval" in out.movies.saved_schedule_secondary.lower()


def test_last_finished_from_persisted_terminal_row_only() -> None:
    base = MediaMopSettings.load()
    s = replace(base, refiner_worker_count=1)
    t_done = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
    with _session() as db:
        db.execute(delete(RefinerJob).where(RefinerJob.dedupe_key == RADARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY))
        db.add(
            RefinerJob(
                dedupe_key=RADARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY,
                job_kind=FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE,
                status=RefinerJobStatus.COMPLETED.value,
                attempt_count=1,
                updated_at=t_done,
            ),
        )
        db.commit()
        out = build_fetcher_failed_import_automation_summary(db, s)
    got = out.movies.last_finished_at
    assert got is not None
    if got.tzinfo is None:
        got = got.replace(tzinfo=timezone.utc)
    assert got == t_done
    assert out.movies.last_outcome_label == "Completed"
