"""Operator POST for manual Refiner file remux pass enqueue (``refiner_jobs`` only)."""

from __future__ import annotations

from sqlalchemy import delete, select
from starlette.testclient import TestClient

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.refiner.jobs_model import RefinerJob
from mediamop.modules.refiner.refiner_file_remux_pass_job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from tests.integration_helpers import auth_post, csrf as fetch_csrf

import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401


def _fac():
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    return create_session_factory(eng)


def _clear_refiner_jobs() -> None:
    fac = _fac()
    with fac() as db:
        db.execute(delete(RefinerJob))
        db.commit()


def _login_admin(client: TestClient) -> None:
    tok = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


def test_refiner_file_remux_pass_enqueue_defaults_dry_run_true(client_with_admin: TestClient) -> None:
    _clear_refiner_jobs()
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r = auth_post(
        client_with_admin,
        "/api/v1/refiner/jobs/file-remux-pass/enqueue",
        json={
            "csrf_token": tok,
            "relative_media_path": "movies/sample.mkv",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["job_kind"] == REFINER_FILE_REMUX_PASS_JOB_KIND
    fac = _fac()
    with fac() as db:
        row = db.scalars(select(RefinerJob).where(RefinerJob.id == body["job_id"])).first()
        assert row is not None
        assert row.job_kind == REFINER_FILE_REMUX_PASS_JOB_KIND
        assert '"dry_run":true' in (row.payload_json or "")
