from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.refiner_file_remux_pass_job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.platform.activity import constants as activity_constants
from mediamop.platform.activity.models import ActivityEvent
from tests.integration_helpers import auth_post, csrf as fetch_csrf


def _login(client: TestClient) -> None:
    tok = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


def test_refiner_overview_stats_requires_auth(client_with_admin: TestClient) -> None:
    r = client_with_admin.get("/api/v1/refiner/overview-stats")
    assert r.status_code == 401


def test_refiner_overview_stats_shape(client_with_admin: TestClient) -> None:
    _login(client_with_admin)
    r = client_with_admin.get("/api/v1/refiner/overview-stats")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["window_days"] == 30
    assert "files_processed" in body
    assert "files_failed" in body
    assert isinstance(body["files_failed"], int)
    assert "success_rate_percent" in body
    assert body["output_written_count"] == 0
    assert body["already_optimized_count"] == 0
    assert body["net_space_saved_bytes"] == 0
    assert body["net_space_saved_percent"] == 0.0


def test_refiner_overview_stats_aggregates_remux_savings(client_with_admin: TestClient) -> None:
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    home = Path(settings.mediamop_home)
    out1 = home / "stats-out-1.mkv"
    out2 = home / "stats-out-2.mkv"
    unchanged = home / "stats-unchanged.mkv"
    for p in (out1, out2, unchanged):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"ok")
    with fac() as db:
        assert isinstance(db, Session)
        db.execute(delete(ActivityEvent))
        db.add_all(
            [
                ActivityEvent(
                    event_type=activity_constants.REFINER_FILE_REMUX_PASS_COMPLETED,
                    module="refiner",
                    title="Remux one",
                    detail=json.dumps(
                        {
                            "outcome": "live_output_written",
                            "source_size_bytes": 1_000,
                            "output_size_bytes": 700,
                            "output_file": str(out1),
                        },
                        separators=(",", ":"),
                    ),
                ),
                ActivityEvent(
                    event_type=activity_constants.REFINER_FILE_REMUX_PASS_COMPLETED,
                    module="refiner",
                    title="Remux two",
                    detail=json.dumps(
                        {
                            "outcome": "live_output_written",
                            "source_size_bytes": 2_000,
                            "output_size_bytes": 1_200,
                            "output_file": str(out2),
                        },
                        separators=(",", ":"),
                    ),
                ),
                ActivityEvent(
                    event_type=activity_constants.REFINER_FILE_REMUX_PASS_COMPLETED,
                    module="refiner",
                    title="Already optimized",
                    detail=json.dumps(
                        {
                            "outcome": "live_skipped_not_required",
                            "output_copied_without_remux": True,
                            "output_file": str(unchanged),
                        },
                        separators=(",", ":"),
                    ),
                ),
            ]
        )
        db.commit()

    _login(client_with_admin)
    r = client_with_admin.get("/api/v1/refiner/overview-stats")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["output_written_count"] == 2
    assert body["already_optimized_count"] == 1
    assert body["files_processed"] == 3
    assert body["net_space_saved_bytes"] == 1_100
    assert body["net_space_saved_percent"] == 36.7


def test_refiner_overview_stats_excludes_non_finalized_successes(client_with_admin: TestClient) -> None:
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    home = Path(settings.mediamop_home)
    finalized = home / "stats-finalized.mkv"
    finalized.parent.mkdir(parents=True, exist_ok=True)
    finalized.write_bytes(b"ok")
    missing = home / "stats-missing.mkv"
    with fac() as db:
        db.execute(delete(ActivityEvent))
        db.query(RefinerJob).delete()
        db.add_all(
            [
                RefinerJob(
                    dedupe_key="completed-job-without-finalized-activity",
                    job_kind=REFINER_FILE_REMUX_PASS_JOB_KIND,
                    status=RefinerJobStatus.COMPLETED.value,
                    payload_json='{"relative_media_path":"SeenOnly.mkv"}',
                ),
                RefinerJob(
                    dedupe_key="failed-job",
                    job_kind=REFINER_FILE_REMUX_PASS_JOB_KIND,
                    status=RefinerJobStatus.FAILED.value,
                    payload_json='{"relative_media_path":"Failed.mkv"}',
                ),
            ]
        )
        db.add_all(
            [
                ActivityEvent(
                    event_type=activity_constants.REFINER_FILE_REMUX_PASS_COMPLETED,
                    module="refiner",
                    title="Finalized",
                    detail=json.dumps(
                        {
                            "outcome": "live_output_written",
                            "source_size_bytes": 100,
                            "output_size_bytes": 80,
                            "output_file": str(finalized),
                        },
                        separators=(",", ":"),
                    ),
                ),
                ActivityEvent(
                    event_type=activity_constants.REFINER_FILE_REMUX_PASS_COMPLETED,
                    module="refiner",
                    title="Missing output",
                    detail=json.dumps(
                        {
                            "outcome": "live_output_written",
                            "source_size_bytes": 100,
                            "output_size_bytes": 80,
                            "output_file": str(missing),
                        },
                        separators=(",", ":"),
                    ),
                ),
                ActivityEvent(
                    event_type=activity_constants.REFINER_FILE_REMUX_PASS_COMPLETED,
                    module="refiner",
                    title="No-change detected only",
                    detail=json.dumps(
                        {
                            "outcome": "live_skipped_not_required",
                            "output_copied_without_remux": False,
                            "output_file": str(finalized),
                        },
                        separators=(",", ":"),
                    ),
                ),
            ]
        )
        db.commit()

    _login(client_with_admin)
    r = client_with_admin.get("/api/v1/refiner/overview-stats")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["files_processed"] == 1
    assert body["output_written_count"] == 1
    assert body["already_optimized_count"] == 0
    assert body["files_failed"] == 1
