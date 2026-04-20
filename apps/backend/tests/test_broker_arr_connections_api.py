"""HTTP: ``/api/v1/broker/connections``."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from starlette.testclient import TestClient

from mediamop.api.factory import create_app
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.core.config import MediaMopSettings
from mediamop.modules.broker.broker_job_kinds import (
    BROKER_JOB_KIND_SYNC_RADARR_MANUAL_V1,
    BROKER_JOB_KIND_SYNC_SONARR_MANUAL_V1,
)
from tests.integration_app_runtime_quiesce import (
    integration_test_quiesce_in_process_workers,
    integration_test_quiesce_periodic_enqueue,
    integration_test_set_home,
)
from tests.integration_helpers import auth_post, auth_put, csrf, seed_admin_user, trusted_browser_origin_headers


@pytest.fixture(autouse=True)
def _isolated_broker_connections_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    integration_test_set_home(tmp_path, monkeypatch, "mmhome_broker_connections_api")
    integration_test_quiesce_in_process_workers(monkeypatch)
    integration_test_quiesce_periodic_enqueue(monkeypatch)
    backend = Path(__file__).resolve().parents[1]
    command.upgrade(Config(str(backend / "alembic.ini")), "head")


@pytest.fixture
def client_admin() -> TestClient:
    seed_admin_user()
    app = create_app()
    with TestClient(app) as c:
        yield c


def _login_admin(c: TestClient) -> None:
    tok = csrf(c)
    r = auth_post(
        c,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


def test_get_sonarr_and_radarr_connections(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    rs = client_admin.get("/api/v1/broker/connections/sonarr", headers=trusted_browser_origin_headers())
    rr = client_admin.get("/api/v1/broker/connections/radarr", headers=trusted_browser_origin_headers())
    assert rs.status_code == 200, rs.text
    assert rr.status_code == 200, rr.text
    assert rs.json()["arr_type"] == "sonarr"
    assert rr.json()["arr_type"] == "radarr"


def test_put_connections_independent(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    tok = csrf(client_admin)
    r1 = auth_put(
        client_admin,
        "/api/v1/broker/connections/sonarr",
        json={"url": "http://sonarr", "api_key": "skey", "csrf_token": tok},
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["url"] == "http://sonarr"
    assert r1.json()["api_key"] == ""

    tok2 = csrf(client_admin)
    r2 = auth_put(
        client_admin,
        "/api/v1/broker/connections/radarr",
        json={"url": "http://radarr", "api_key": "rkey", "csrf_token": tok2},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["url"] == "http://radarr"

    rs = client_admin.get("/api/v1/broker/connections/sonarr", headers=trusted_browser_origin_headers())
    assert rs.json()["url"] == "http://sonarr"
    rr = client_admin.get("/api/v1/broker/connections/radarr", headers=trusted_browser_origin_headers())
    assert rr.json()["url"] == "http://radarr"


def test_post_sync_enqueues_correct_manual_kind(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    tok = csrf(client_admin)
    r1 = auth_post(
        client_admin,
        "/api/v1/broker/connections/sonarr/sync",
        json={"csrf_token": tok},
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["job_kind"] == BROKER_JOB_KIND_SYNC_SONARR_MANUAL_V1

    tok2 = csrf(client_admin)
    r2 = auth_post(
        client_admin,
        "/api/v1/broker/connections/radarr/sync",
        json={"csrf_token": tok2},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["job_kind"] == BROKER_JOB_KIND_SYNC_RADARR_MANUAL_V1


def test_sonarr_sync_http_failure_does_not_mutate_radarr_state() -> None:
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    with fac() as db:
        from mediamop.modules.broker.broker_arr_connections_service import get_connection, update_connection
        from mediamop.modules.broker.broker_jobs_ops import broker_enqueue_or_get_job
        from mediamop.modules.broker.broker_schemas import BrokerArrConnectionUpdate

        rad_before = get_connection(db, "radarr")
        fp_before = rad_before.indexer_fingerprint
        manual_ok_before = rad_before.last_manual_sync_ok
        update_connection(
            db,
            "sonarr",
            BrokerArrConnectionUpdate(url="http://sonarr.invalid", api_key="k"),
        )
        broker_enqueue_or_get_job(
            db,
            dedupe_key="pytest:sonarr:manual:fail:1",
            job_kind=BROKER_JOB_KIND_SYNC_SONARR_MANUAL_V1,
        )
        db.commit()

    def boom(*_a, **_k):
        raise RuntimeError("sonarr http boom")

    with patch(
        "mediamop.modules.broker.broker_sync_job_handler.apply_broker_indexers_to_arr",
        side_effect=boom,
    ):
        from mediamop.modules.broker.broker_job_handlers import build_broker_job_handlers
        from mediamop.modules.broker.broker_worker_loop import process_one_broker_job

        handlers = build_broker_job_handlers(settings, fac)
        assert (
            process_one_broker_job(
                fac,
                lease_owner="pytest-sonarr-fail",
                job_handlers=handlers,
            )
            == "processed"
        )

    with fac() as db:
        rad_after = get_connection(db, "radarr")
        assert rad_after.indexer_fingerprint == fp_before
        assert rad_after.last_manual_sync_ok == manual_ok_before
