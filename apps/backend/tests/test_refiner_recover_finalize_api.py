"""Refiner Pass 20: POST /refiner/jobs/{id}/recover-finalize-failure."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from starlette.testclient import TestClient

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.refiner.jobs_ops import (
    claim_next_eligible_refiner_job,
    fail_claimed_refiner_job,
    fail_leased_refiner_job_after_complete_failure,
    refiner_enqueue_or_get_job,
)
from tests.integration_helpers import auth_post, csrf as fetch_csrf

import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401


def _fac():
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    return create_session_factory(eng)


def _t0() -> datetime:
    return datetime(2026, 4, 12, 12, 0, 0, tzinfo=timezone.utc)


def _login_admin(client: TestClient) -> None:
    tok = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


def _seed_finalize_failed_job() -> int:
    t0 = _t0()
    fac = _fac()
    with fac() as db:
        db.execute(delete(RefinerJob))
        db.commit()
    with fac() as db:
        refiner_enqueue_or_get_job(db, dedupe_key="recover-api", job_kind="k.recover")
        db.commit()
    with fac() as db:
        j = claim_next_eligible_refiner_job(
            db,
            lease_owner="w",
            lease_expires_at=t0 + timedelta(hours=1),
            now=t0,
        )
        assert j is not None
        jid = j.id
        fail_leased_refiner_job_after_complete_failure(
            db,
            job_id=jid,
            lease_owner="w",
            error_message="refiner_terminalization_failure: x",
            now=t0,
        )
        db.commit()
    return jid


def test_recover_finalize_success(client_with_admin: TestClient) -> None:
    jid = _seed_finalize_failed_job()
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r = auth_post(
        client_with_admin,
        f"/api/v1/refiner/jobs/{jid}/recover-finalize-failure",
        json={"confirm": True, "csrf_token": tok},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["job_id"] == jid
    assert body["status"] == RefinerJobStatus.COMPLETED.value
    fac = _fac()
    with fac() as db:
        row = db.get(RefinerJob, jid)
        assert row is not None
        assert row.status == RefinerJobStatus.COMPLETED.value


def test_recover_finalize_409_when_not_finalize_failed(client_with_admin: TestClient) -> None:
    t0 = _t0()
    fac = _fac()
    with fac() as db:
        db.execute(delete(RefinerJob))
        db.commit()
    with fac() as db:
        refiner_enqueue_or_get_job(db, dedupe_key="recover-bad", job_kind="k", max_attempts=1)
        db.commit()
    with fac() as db:
        j = claim_next_eligible_refiner_job(
            db,
            lease_owner="w",
            lease_expires_at=t0 + timedelta(hours=1),
            now=t0,
        )
        jid = j.id
        fail_claimed_refiner_job(
            db,
            job_id=jid,
            lease_owner="w",
            error_message="boom",
            now=t0,
        )
        db.commit()

    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r = auth_post(
        client_with_admin,
        f"/api/v1/refiner/jobs/{jid}/recover-finalize-failure",
        json={"confirm": True, "csrf_token": tok},
    )
    assert r.status_code == 409, r.text


def test_recover_finalize_404_missing_job(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r = auth_post(
        client_with_admin,
        "/api/v1/refiner/jobs/999999/recover-finalize-failure",
        json={"confirm": True, "csrf_token": tok},
    )
    assert r.status_code == 404


def test_recover_finalize_403_viewer(client_with_viewer: TestClient) -> None:
    jid = _seed_finalize_failed_job()
    tok = fetch_csrf(client_with_viewer)
    r_login = auth_post(
        client_with_viewer,
        "/api/v1/auth/login",
        json={"username": "bob", "password": "viewer-password-here", "csrf_token": tok},
    )
    assert r_login.status_code == 200, r_login.text
    tok2 = fetch_csrf(client_with_viewer)
    r = auth_post(
        client_with_viewer,
        f"/api/v1/refiner/jobs/{jid}/recover-finalize-failure",
        json={"confirm": True, "csrf_token": tok2},
    )
    assert r.status_code == 403


def test_recover_finalize_rejects_invalid_csrf(client_with_admin: TestClient) -> None:
    jid = _seed_finalize_failed_job()
    _login_admin(client_with_admin)
    r = auth_post(
        client_with_admin,
        f"/api/v1/refiner/jobs/{jid}/recover-finalize-failure",
        json={"confirm": True, "csrf_token": "not-valid"},
    )
    assert r.status_code == 400
