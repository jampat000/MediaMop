"""Operator POST for manual Trimmer supplied trim plan JSON file write enqueue (``trimmer_jobs`` only)."""

from __future__ import annotations

from sqlalchemy import delete, select
from starlette.testclient import TestClient

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.trimmer.trimmer_jobs_model import TrimmerJob
from mediamop.modules.trimmer.trimmer_supplied_trim_plan_json_file_write_job_kinds import (
    TRIMMER_SUPPLIED_TRIM_PLAN_JSON_FILE_WRITE_JOB_KIND,
)
from tests.integration_helpers import auth_post, csrf as fetch_csrf

import mediamop.modules.trimmer.trimmer_jobs_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401


def _fac():
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    return create_session_factory(eng)


def _clear_trimmer_jobs() -> None:
    fac = _fac()
    with fac() as db:
        db.execute(delete(TrimmerJob))
        db.commit()


def _login_admin(client: TestClient) -> None:
    tok = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


def test_trimmer_supplied_trim_plan_json_file_write_enqueue_admin_ok(client_with_admin: TestClient) -> None:
    _clear_trimmer_jobs()
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r = auth_post(
        client_with_admin,
        "/api/v1/trimmer/jobs/supplied-trim-plan-json-file-write/enqueue",
        json={
            "csrf_token": tok,
            "segments": [{"start_sec": 0, "end_sec": 12.5}],
            "source_duration_sec": 100,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["job_kind"] == TRIMMER_SUPPLIED_TRIM_PLAN_JSON_FILE_WRITE_JOB_KIND
    fac = _fac()
    with fac() as db:
        row = db.scalars(select(TrimmerJob).where(TrimmerJob.id == body["job_id"])).first()
        assert row is not None
        assert row.job_kind == TRIMMER_SUPPLIED_TRIM_PLAN_JSON_FILE_WRITE_JOB_KIND
