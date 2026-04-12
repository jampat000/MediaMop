"""Operator POST for Refiner candidate gate enqueue (``refiner_jobs`` only)."""

from __future__ import annotations

from sqlalchemy import delete, select
from starlette.testclient import TestClient

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.refiner.jobs_model import RefinerJob
from mediamop.modules.refiner.refiner_candidate_gate_job_kinds import REFINER_CANDIDATE_GATE_JOB_KIND
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


def test_refiner_candidate_gate_enqueue_admin_ok(client_with_admin: TestClient) -> None:
    _clear_refiner_jobs()
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r = auth_post(
        client_with_admin,
        "/api/v1/refiner/jobs/candidate-gate/enqueue",
        json={
            "target": "radarr",
            "release_title": "Example Movie 2020",
            "release_year": 2020,
            "csrf_token": tok,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["job_kind"] == REFINER_CANDIDATE_GATE_JOB_KIND
    assert body["dedupe_key"].startswith(f"{REFINER_CANDIDATE_GATE_JOB_KIND}:")
    fac = _fac()
    with fac() as db:
        row = db.scalars(select(RefinerJob).where(RefinerJob.id == body["job_id"])).first()
        assert row is not None
        assert row.job_kind == REFINER_CANDIDATE_GATE_JOB_KIND


def test_refiner_candidate_gate_enqueue_rejects_series_id_for_radarr(
    client_with_admin: TestClient,
) -> None:
    _clear_refiner_jobs()
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r = auth_post(
        client_with_admin,
        "/api/v1/refiner/jobs/candidate-gate/enqueue",
        json={
            "target": "radarr",
            "release_title": "X",
            "series_id": 1,
            "csrf_token": tok,
        },
    )
    assert r.status_code == 422, r.text
