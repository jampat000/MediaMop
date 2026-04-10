"""Authenticated read-only ``GET /api/v1/refiner/jobs/inspection``."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete
from starlette.testclient import TestClient

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
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


def _seed_mixed_status_rows() -> None:
    t0 = datetime(2026, 4, 11, 10, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 4, 11, 11, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 4, 11, 12, 0, 0, tzinfo=timezone.utc)
    fac = _fac()
    with fac() as db:
        db.execute(delete(RefinerJob))
        db.commit()
    with fac() as db:
        db.add(
            RefinerJob(
                dedupe_key="insp-pending",
                job_kind="k.pending",
                status=RefinerJobStatus.PENDING.value,
                updated_at=t0,
            ),
        )
        db.add(
            RefinerJob(
                dedupe_key="insp-leased",
                job_kind="k.leased",
                status=RefinerJobStatus.LEASED.value,
                lease_owner="w1",
                lease_expires_at=t2,
                attempt_count=1,
                updated_at=t0,
            ),
        )
        db.add(
            RefinerJob(
                dedupe_key="insp-done",
                job_kind="k.done",
                status=RefinerJobStatus.COMPLETED.value,
                attempt_count=1,
                updated_at=t2,
            ),
        )
        db.add(
            RefinerJob(
                dedupe_key="insp-fail",
                job_kind="k.fail",
                status=RefinerJobStatus.FAILED.value,
                attempt_count=2,
                max_attempts=2,
                last_error="handler boom",
                updated_at=t1,
            ),
        )
        db.add(
            RefinerJob(
                dedupe_key="insp-finalize",
                job_kind="k.finalize",
                status=RefinerJobStatus.HANDLER_OK_FINALIZE_FAILED.value,
                attempt_count=1,
                last_error="refiner_terminalization_failure: db",
                updated_at=t2,
            ),
        )
        db.commit()


def test_refiner_jobs_inspection_requires_auth(client_with_admin: TestClient) -> None:
    r = client_with_admin.get("/api/v1/refiner/jobs/inspection")
    assert r.status_code == 401


def test_refiner_jobs_inspection_default_returns_only_terminal_states(client_with_admin: TestClient) -> None:
    _seed_mixed_status_rows()
    _login(client_with_admin)
    r = client_with_admin.get("/api/v1/refiner/jobs/inspection?limit=20")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["default_terminal_only"] is True
    jobs = body["jobs"]
    kinds = {j["job_kind"] for j in jobs}
    assert "k.pending" not in kinds
    assert "k.leased" not in kinds
    assert "k.done" in kinds
    assert "k.fail" in kinds
    assert "k.finalize" in kinds
    by_kind = {j["job_kind"]: j for j in jobs}
    assert by_kind["k.fail"]["status"] == RefinerJobStatus.FAILED.value
    assert by_kind["k.finalize"]["status"] == RefinerJobStatus.HANDLER_OK_FINALIZE_FAILED.value
    assert by_kind["k.finalize"]["status"] != RefinerJobStatus.FAILED.value
    assert by_kind["k.done"]["status"] == RefinerJobStatus.COMPLETED.value
    for j in jobs:
        assert "dedupe_key" in j
        assert "attempt_count" in j
        assert "max_attempts" in j
        assert "lease_owner" in j
        assert "lease_expires_at" in j
        assert "last_error" in j
        assert "created_at" in j
        assert "updated_at" in j


def test_refiner_jobs_inspection_status_filter_includes_pending(client_with_admin: TestClient) -> None:
    _seed_mixed_status_rows()
    _login(client_with_admin)
    r = client_with_admin.get("/api/v1/refiner/jobs/inspection?status=pending&limit=10")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["default_terminal_only"] is False
    assert len(body["jobs"]) >= 1
    assert all(j["status"] == RefinerJobStatus.PENDING.value for j in body["jobs"])


def test_refiner_jobs_inspection_invalid_status_422(client_with_admin: TestClient) -> None:
    _login(client_with_admin)
    r = client_with_admin.get("/api/v1/refiner/jobs/inspection?status=not_a_real_status")
    assert r.status_code == 422
