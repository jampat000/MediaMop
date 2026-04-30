from __future__ import annotations

import json

from sqlalchemy import select
from starlette.testclient import TestClient

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.pruner.pruner_jobs_model import PrunerJob, PrunerJobStatus
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.subber.subber_jobs_model import SubberJob, SubberJobStatus
from mediamop.platform.activity import constants as activity_constants
from mediamop.platform.activity.models import ActivityEvent
from tests.integration_helpers import auth_post, csrf as fetch_csrf


def _login(client: TestClient) -> str:
    tok = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text
    return fetch_csrf(client)


def test_operational_history_reset_requires_confirmation(client_with_admin: TestClient) -> None:
    token = _login(client_with_admin)
    r = auth_post(
        client_with_admin,
        "/api/v1/suite/operational-history/reset",
        json={"csrf_token": token, "confirm": "wrong"},
    )
    assert r.status_code == 400
    assert "RESET" in r.json()["detail"]


def test_operational_history_reset_clears_history_but_keeps_active_work(client_with_admin: TestClient) -> None:
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    with fac() as db:
        db.query(ActivityEvent).delete()
        db.query(RefinerJob).delete()
        db.query(PrunerJob).delete()
        db.query(SubberJob).delete()
        db.add(
            ActivityEvent(
                event_type=activity_constants.REFINER_FILE_REMUX_PASS_COMPLETED,
                module="refiner",
                title="Finished file",
                detail=json.dumps({"outcome": "live_output_written"}),
            )
        )
        db.add_all(
            [
                RefinerJob(dedupe_key="refiner-done", job_kind="refiner.file.remux_pass.v1", status=RefinerJobStatus.COMPLETED.value),
                RefinerJob(dedupe_key="refiner-pending", job_kind="refiner.file.remux_pass.v1", status=RefinerJobStatus.PENDING.value),
                PrunerJob(dedupe_key="pruner-done", job_kind="pruner.preview", status=PrunerJobStatus.FAILED.value),
                PrunerJob(dedupe_key="pruner-pending", job_kind="pruner.preview", status=PrunerJobStatus.PENDING.value),
                SubberJob(dedupe_key="subber-done", job_kind="subber.search", status=SubberJobStatus.COMPLETED.value),
                SubberJob(dedupe_key="subber-pending", job_kind="subber.search", status=SubberJobStatus.PENDING.value),
            ]
        )
        db.commit()

    token = _login(client_with_admin)
    r = auth_post(
        client_with_admin,
        "/api/v1/suite/operational-history/reset",
        json={"csrf_token": token, "confirm": "RESET"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "reset"
    assert body["activity_events_deleted"] >= 1
    assert body["refiner_jobs_deleted"] == 1
    assert body["pruner_jobs_deleted"] == 1
    assert body["subber_jobs_deleted"] == 1

    with fac() as db:
        assert db.scalars(select(ActivityEvent)).first() is None
        assert db.scalar(select(RefinerJob).where(RefinerJob.dedupe_key == "refiner-done")) is None
        assert db.scalar(select(PrunerJob).where(PrunerJob.dedupe_key == "pruner-done")) is None
        assert db.scalar(select(SubberJob).where(SubberJob.dedupe_key == "subber-done")) is None
        assert db.scalar(select(RefinerJob).where(RefinerJob.dedupe_key == "refiner-pending")) is not None
        assert db.scalar(select(PrunerJob).where(PrunerJob.dedupe_key == "pruner-pending")) is not None
        assert db.scalar(select(SubberJob).where(SubberJob.dedupe_key == "subber-pending")) is not None
