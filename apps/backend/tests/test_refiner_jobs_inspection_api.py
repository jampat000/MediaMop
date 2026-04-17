"""``GET /api/v1/refiner/jobs/inspection`` + ``POST …/cancel-pending`` (``refiner_jobs`` lane)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete
from starlette.testclient import TestClient

from mediamop.api.factory import create_app
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from tests.integration_app_runtime_quiesce import (
    integration_test_quiesce_in_process_workers,
    integration_test_quiesce_periodic_enqueue,
    integration_test_set_home,
)
from tests.integration_helpers import auth_post, csrf as fetch_csrf, seed_admin_user, seed_viewer_user

import mediamop.modules.refiner.jobs_model  # noqa: F401
import mediamop.platform.activity.models  # noqa: F401
import mediamop.platform.auth.models  # noqa: F401


@pytest.fixture(autouse=True)
def _isolated_refiner_jobs_inspection_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use a per-test MEDIAMOP_HOME so jobs rows cannot race with other tests/apps."""

    integration_test_set_home(tmp_path, monkeypatch, "mediamop_home")
    integration_test_quiesce_in_process_workers(monkeypatch)
    # Keep all periodic enqueue loops off in this file to ensure deterministic inspection slices.
    integration_test_quiesce_periodic_enqueue(monkeypatch)

    backend = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend / "alembic.ini"))
    command.upgrade(cfg, "head")


@pytest.fixture
def client_with_admin() -> TestClient:
    seed_admin_user()
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_with_viewer() -> TestClient:
    seed_viewer_user()
    app = create_app()
    with TestClient(app) as c:
        yield c


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


def _login_viewer(client: TestClient) -> None:
    tok = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "bob", "password": "viewer-password-here", "csrf_token": tok},
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
                dedupe_key="rinsp-pending",
                job_kind="refiner.candidate_gate.v1",
                status=RefinerJobStatus.PENDING.value,
                updated_at=t0,
            ),
        )
        db.add(
            RefinerJob(
                dedupe_key="rinsp-leased",
                job_kind="refiner.file.remux_pass.v1",
                status=RefinerJobStatus.LEASED.value,
                lease_owner="w1",
                lease_expires_at=t2,
                attempt_count=1,
                updated_at=t0,
            ),
        )
        db.add(
            RefinerJob(
                dedupe_key="rinsp-done",
                job_kind="refiner.supplied_payload_evaluation.v1",
                status=RefinerJobStatus.COMPLETED.value,
                attempt_count=1,
                updated_at=t2,
            ),
        )
        db.add(
            RefinerJob(
                dedupe_key="rinsp-fail",
                job_kind="refiner.watched_folder.remux_scan_dispatch.v1",
                status=RefinerJobStatus.FAILED.value,
                attempt_count=2,
                max_attempts=2,
                last_error="handler boom",
                updated_at=t1,
            ),
        )
        db.add(
            RefinerJob(
                dedupe_key="rinsp-finalize",
                job_kind="refiner.file.remux_pass.v1",
                status=RefinerJobStatus.HANDLER_OK_FINALIZE_FAILED.value,
                attempt_count=1,
                last_error="finalize",
                updated_at=t2,
            ),
        )
        db.add(
            RefinerJob(
                dedupe_key="rinsp-cancelled",
                job_kind="refiner.candidate_gate.v1",
                status=RefinerJobStatus.CANCELLED.value,
                updated_at=t1,
            ),
        )
        db.commit()


def test_refiner_jobs_inspection_requires_auth(client_with_admin: TestClient) -> None:
    r = client_with_admin.get("/api/v1/refiner/jobs/inspection")
    assert r.status_code == 401


def test_refiner_jobs_inspection_default_includes_pending_and_leased(
    client_with_admin: TestClient,
) -> None:
    _login(client_with_admin)
    _seed_mixed_status_rows()
    r = client_with_admin.get("/api/v1/refiner/jobs/inspection?limit=20")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["default_recent_slice"] is True
    kinds = {j["job_kind"] for j in body["jobs"]}
    assert "refiner.candidate_gate.v1" in kinds
    statuses = {j["status"] for j in body["jobs"]}
    assert RefinerJobStatus.PENDING.value in statuses
    assert RefinerJobStatus.LEASED.value in statuses
    assert RefinerJobStatus.CANCELLED.value in statuses


def test_refiner_jobs_inspection_status_filter(client_with_admin: TestClient) -> None:
    _seed_mixed_status_rows()
    _login(client_with_admin)
    r = client_with_admin.get("/api/v1/refiner/jobs/inspection?status=pending&limit=10")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["default_recent_slice"] is False
    assert all(j["status"] == RefinerJobStatus.PENDING.value for j in body["jobs"])


def test_refiner_jobs_inspection_invalid_status_422(client_with_admin: TestClient) -> None:
    _login(client_with_admin)
    r = client_with_admin.get("/api/v1/refiner/jobs/inspection?status=not_a_real_status")
    assert r.status_code == 422


def test_refiner_job_cancel_pending_ok(client_with_admin: TestClient) -> None:
    fac = _fac()
    with fac() as db:
        db.execute(delete(RefinerJob))
        db.commit()
    dedupe = f"to-cancel-{__import__('uuid').uuid4().hex}"
    with fac() as db:
        row = RefinerJob(
            dedupe_key=dedupe,
            job_kind="refiner.candidate_gate.v1",
            status=RefinerJobStatus.PENDING.value,
        )
        db.add(row)
        db.flush()
        jid = int(row.id)
        db.commit()

    _login(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r = auth_post(
        client_with_admin,
        f"/api/v1/refiner/jobs/{jid}/cancel-pending",
        json={"csrf_token": tok},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is True
    assert out["status"] == RefinerJobStatus.CANCELLED.value

    with fac() as db:
        row = db.get(RefinerJob, jid)
        assert row is not None
        assert row.status == RefinerJobStatus.CANCELLED.value
        assert ":cancelled:" in row.dedupe_key


def test_refiner_job_cancel_pending_refuses_leased(client_with_admin: TestClient) -> None:
    fac = _fac()
    with fac() as db:
        db.execute(delete(RefinerJob))
        row = RefinerJob(
            dedupe_key="leased-block",
            job_kind="refiner.candidate_gate.v1",
            status=RefinerJobStatus.LEASED.value,
            lease_owner="w",
            lease_expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
            attempt_count=1,
        )
        db.add(row)
        db.flush()
        jid = int(row.id)
        db.commit()

    _login(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r = auth_post(
        client_with_admin,
        f"/api/v1/refiner/jobs/{jid}/cancel-pending",
        json={"csrf_token": tok},
    )
    assert r.status_code == 409


def test_refiner_jobs_inspection_viewer_can_read(client_with_viewer: TestClient) -> None:
    _seed_mixed_status_rows()
    _login_viewer(client_with_viewer)
    r = client_with_viewer.get("/api/v1/refiner/jobs/inspection?limit=5")
    assert r.status_code == 200, r.text
    assert "jobs" in r.json()


def test_refiner_job_cancel_pending_viewer_forbidden(client_with_viewer: TestClient) -> None:
    fac = _fac()
    with fac() as db:
        db.execute(delete(RefinerJob))
        row = RefinerJob(
            dedupe_key="viewer-deny",
            job_kind="refiner.candidate_gate.v1",
            status=RefinerJobStatus.PENDING.value,
        )
        db.add(row)
        db.flush()
        jid = int(row.id)
        db.commit()

    _login_viewer(client_with_viewer)
    tok = fetch_csrf(client_with_viewer)
    r = auth_post(
        client_with_viewer,
        f"/api/v1/refiner/jobs/{jid}/cancel-pending",
        json={"csrf_token": tok},
    )
    assert r.status_code == 403
