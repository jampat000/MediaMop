"""Authenticated read-only ``GET /api/v1/fetcher/failed-imports/automation-summary``."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete
from starlette.testclient import TestClient

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.fetcher.radarr_failed_import_cleanup_job import (
    RADARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY,
    FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE,
)
from mediamop.modules.fetcher.sonarr_failed_import_cleanup_job import (
    FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE,
    SONARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY,
)
from tests.integration_helpers import auth_post, csrf as fetch_csrf

import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401


def _fac():
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    return create_session_factory(eng)


def _login(client: TestClient) -> None:
    tok = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


def _wipe_drive_jobs() -> None:
    fac = _fac()
    with fac() as db:
        db.execute(
            delete(RefinerJob).where(
                RefinerJob.dedupe_key.in_(
                    (
                        RADARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY,
                        SONARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY,
                    ),
                ),
            ),
        )
        db.commit()


def _seed_radarr_completed(*, updated_at: datetime) -> None:
    fac = _fac()
    with fac() as db:
        db.add(
            RefinerJob(
                dedupe_key=RADARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY,
                job_kind=FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE,
                status=RefinerJobStatus.COMPLETED.value,
                attempt_count=1,
                updated_at=updated_at,
            ),
        )
        db.commit()


def _seed_sonarr_failed(*, updated_at: datetime) -> None:
    fac = _fac()
    with fac() as db:
        db.add(
            RefinerJob(
                dedupe_key=SONARR_FAILED_IMPORT_CLEANUP_DRIVE_DEDUPE_KEY,
                job_kind=FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE,
                status=RefinerJobStatus.FAILED.value,
                attempt_count=1,
                max_attempts=3,
                last_error="x",
                updated_at=updated_at,
            ),
        )
        db.commit()


def test_automation_summary_movies_tv_separate_outcomes(client_with_admin: TestClient) -> None:
    _wipe_drive_jobs()
    tr = datetime(2026, 4, 11, 15, 30, 0, tzinfo=timezone.utc)
    ts = datetime(2026, 4, 11, 16, 0, 0, tzinfo=timezone.utc)
    _seed_radarr_completed(updated_at=tr)
    _seed_sonarr_failed(updated_at=ts)
    _login(client_with_admin)
    r = client_with_admin.get("/api/v1/fetcher/failed-imports/automation-summary")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["movies"]["last_outcome_label"] == "Completed"
    assert data["tv_shows"]["last_outcome_label"] == "Stopped after errors"
    assert "2026-04-11T15:30:00" in data["movies"]["last_finished_at"]
    assert "2026-04-11T16:00:00" in data["tv_shows"]["last_finished_at"]


def test_automation_summary_empty_history_clean(client_with_admin: TestClient) -> None:
    _wipe_drive_jobs()
    _login(client_with_admin)
    r = client_with_admin.get("/api/v1/fetcher/failed-imports/automation-summary")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["movies"]["last_finished_at"] is None
    assert data["tv_shows"]["last_finished_at"] is None
    assert "movie pass" in data["movies"]["last_outcome_label"].lower()
    assert "tv pass" in data["tv_shows"]["last_outcome_label"].lower()


def test_automation_summary_no_fake_liveness_phrasing(client_with_admin: TestClient) -> None:
    _login(client_with_admin)
    r = client_with_admin.get("/api/v1/fetcher/failed-imports/automation-summary")
    assert r.status_code == 200, r.text
    blob = r.text.lower()
    assert "healthy" not in blob
    assert "live ok" not in blob
    assert "reachable" not in blob
    data = r.json()
    assert "finished passes" in data["scope_note"].lower() or "saved settings" in data["scope_note"].lower()


def test_automation_summary_slots_zero_note(client_with_admin: TestClient) -> None:
    """Session autouse sets MEDIAMOP_REFINER_WORKER_COUNT=0 for pytest."""

    _login(client_with_admin)
    r = client_with_admin.get("/api/v1/fetcher/failed-imports/automation-summary")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["automation_slots_note"] is not None
    assert "0" in data["automation_slots_note"]
