"""HTTP tests for Broker Torznab/Newznab proxy."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from starlette.testclient import TestClient

from mediamop.api.factory import create_app
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.core.config import MediaMopSettings
from mediamop.modules.broker.broker_settings_service import get_proxy_api_key
from tests.integration_app_runtime_quiesce import (
    integration_test_quiesce_in_process_workers,
    integration_test_quiesce_periodic_enqueue,
    integration_test_set_home,
)
from tests.integration_helpers import csrf, seed_admin_user, trusted_browser_origin_headers


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    integration_test_set_home(tmp_path, monkeypatch, "mmhome_broker_proxy_api")
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


def _login(c: TestClient) -> None:
    tok = csrf(c)
    c.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
        headers=trusted_browser_origin_headers(),
    )


def _api_key() -> str:
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    with fac() as db:
        return get_proxy_api_key(db)


def test_torznab_missing_apikey_401(client_admin: TestClient) -> None:
    r = client_admin.get("/api/v1/broker/torznab?t=search&q=test")
    assert r.status_code == 401


def test_torznab_valid_apikey_returns_xml(client_admin: TestClient) -> None:
    key = _api_key()
    r = client_admin.get(
        f"/api/v1/broker/torznab?apikey={key}&t=search&q=test",
        headers=trusted_browser_origin_headers(),
    )
    assert r.status_code == 200, r.text
    assert "application/rss" in (r.headers.get("content-type") or "")
    assert b"<rss" in r.content.lower() or b"<caps" in r.content.lower()


def test_newznab_valid_apikey_returns_json(client_admin: TestClient) -> None:
    key = _api_key()
    r = client_admin.get(
        f"/api/v1/broker/newznab?apikey={key}&t=search&q=test",
        headers=trusted_browser_origin_headers(),
    )
    assert r.status_code == 200, r.text
    assert "application/json" in (r.headers.get("content-type") or "")
    body = r.json()
    assert "channel" in body


def test_proxy_apikey_endpoint_returns_key(client_admin: TestClient) -> None:
    _login(client_admin)
    r = client_admin.get("/api/v1/broker/proxy/apikey", headers=trusted_browser_origin_headers())
    assert r.status_code == 200, r.text
    assert r.json()["proxy_api_key"] == _api_key()


def test_proxy_apikey_rotate_changes_key(client_admin: TestClient) -> None:
    _login(client_admin)
    before = _api_key()
    tok = csrf(client_admin)
    r = client_admin.post(
        "/api/v1/broker/proxy/apikey/rotate",
        json={"csrf_token": tok},
        headers=trusted_browser_origin_headers(),
    )
    assert r.status_code == 200, r.text
    after = r.json()["proxy_api_key"]
    assert after != before
    assert after == _api_key()
