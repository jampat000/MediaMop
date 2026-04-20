"""HTTP: ``/api/v1/broker/indexers``."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from starlette.testclient import TestClient

from mediamop.api.factory import create_app
from tests.integration_app_runtime_quiesce import (
    integration_test_quiesce_in_process_workers,
    integration_test_quiesce_periodic_enqueue,
    integration_test_set_home,
)
from tests.integration_helpers import auth_post, auth_put, csrf, seed_admin_user, trusted_browser_origin_headers


@pytest.fixture(autouse=True)
def _isolated_broker_indexers_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    integration_test_set_home(tmp_path, monkeypatch, "mmhome_broker_indexers_api")
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


def test_broker_indexers_crud_and_enqueue_on_enable_toggle(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    tok = csrf(client_admin)

    r0 = client_admin.get("/api/v1/broker/indexers", headers=trusted_browser_origin_headers())
    assert r0.status_code == 200, r0.text
    assert r0.json() == []

    create_body = {
        "name": "YTS",
        "slug": "native__yts",
        "kind": "native__yts",
        "protocol": "torrent",
        "privacy": "public",
        "url": "https://example.invalid/",
        "api_key": "secret",
        "enabled": False,
        "priority": 10,
        "categories": [2000],
        "tags": ["movies"],
        "csrf_token": tok,
    }
    r1 = auth_post(client_admin, "/api/v1/broker/indexers", json=create_body)
    assert r1.status_code == 200, r1.text
    row = r1.json()
    assert row["id"] == 1
    assert row["slug"] == "native__yts"
    assert row["api_key"] == ""
    assert row["enabled"] is False
    assert row["categories"] == [2000]

    r2 = client_admin.get("/api/v1/broker/indexers/1", headers=trusted_browser_origin_headers())
    assert r2.status_code == 200, r2.text
    assert r2.json()["name"] == "YTS"

    tok2 = csrf(client_admin)
    r3 = auth_put(
        client_admin,
        "/api/v1/broker/indexers/1",
        json={"name": "YTS (upd)", "enabled": True, "csrf_token": tok2},
    )
    assert r3.status_code == 200, r3.text
    assert r3.json()["enabled"] is True

    r_jobs = client_admin.get("/api/v1/broker/jobs", headers=trusted_browser_origin_headers())
    assert r_jobs.status_code == 200, r_jobs.text
    kinds = {j["job_kind"] for j in r_jobs.json()["jobs"]}
    assert "broker.sync.sonarr.v1" in kinds
    assert "broker.sync.radarr.v1" in kinds

    tok3 = csrf(client_admin)
    r4 = auth_put(
        client_admin,
        "/api/v1/broker/indexers/1",
        json={"enabled": False, "csrf_token": tok3},
    )
    assert r4.status_code == 200, r4.text
    r_jobs2 = client_admin.get("/api/v1/broker/jobs", headers=trusted_browser_origin_headers())
    assert r_jobs2.status_code == 200, r_jobs2.text
    kinds2 = [j["job_kind"] for j in r_jobs2.json()["jobs"]]
    assert kinds2.count("broker.sync.sonarr.v1") >= 2
    assert kinds2.count("broker.sync.radarr.v1") >= 2

    r5 = client_admin.delete("/api/v1/broker/indexers/1", headers=trusted_browser_origin_headers())
    assert r5.status_code == 204, r5.text

    r6 = client_admin.get("/api/v1/broker/indexers/1", headers=trusted_browser_origin_headers())
    assert r6.status_code == 404


def test_broker_indexer_test_enqueue(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    tok = csrf(client_admin)
    create_body = {
        "name": "Probe",
        "slug": "torznab__x",
        "kind": "torznab",
        "protocol": "torrent",
        "csrf_token": tok,
    }
    r1 = auth_post(client_admin, "/api/v1/broker/indexers", json=create_body)
    assert r1.status_code == 200, r1.text
    iid = int(r1.json()["id"])
    tok2 = csrf(client_admin)
    r2 = auth_post(
        client_admin,
        f"/api/v1/broker/indexers/{iid}/test",
        json={"csrf_token": tok2},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "enqueued"
