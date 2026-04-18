"""HTTP: ``/api/v1/subber/settings`` and connection tests."""

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
from tests.integration_helpers import auth_post, csrf, seed_admin_user, seed_viewer_user, trusted_browser_origin_headers


@pytest.fixture(autouse=True)
def _isolated_subber_settings_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    integration_test_set_home(tmp_path, monkeypatch, "mmhome_subber_settings_api")
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


@pytest.fixture
def client_viewer() -> TestClient:
    seed_viewer_user()
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


def _login_viewer(c: TestClient) -> None:
    tok = csrf(c)
    r = auth_post(
        c,
        "/api/v1/auth/login",
        json={"username": "bob", "password": "viewer-password-here", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


def test_get_settings_requires_auth(client_admin: TestClient) -> None:
    r = client_admin.get("/api/v1/subber/settings")
    assert r.status_code == 401


def test_get_settings_requires_operator(client_viewer: TestClient) -> None:
    _login_viewer(client_viewer)
    r = client_viewer.get("/api/v1/subber/settings")
    assert r.status_code == 403


def test_get_settings_admin_ok(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    r = client_admin.get("/api/v1/subber/settings")
    assert r.status_code == 200
    body = r.json()
    assert "opensubtitles_username" in body
    assert body.get("opensubtitles_password_set") is False


def test_put_settings_roundtrip_enabled(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    tok = csrf(client_admin)
    r_put = client_admin.put(
        "/api/v1/subber/settings",
        json={"enabled": True, "csrf_token": tok},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r_put.status_code == 200, r_put.text
    assert r_put.json().get("enabled") is True


def test_test_opensubtitles_requires_operator(client_viewer: TestClient) -> None:
    _login_viewer(client_viewer)
    tok = csrf(client_viewer)
    r = auth_post(
        client_viewer,
        "/api/v1/subber/settings/test-opensubtitles",
        json={"csrf_token": tok},
    )
    assert r.status_code == 403


def test_test_opensubtitles_missing_creds(client_admin: TestClient) -> None:
    _login_admin(client_admin)
    tok = csrf(client_admin)
    r = client_admin.post(
        "/api/v1/subber/settings/test-opensubtitles",
        json={"csrf_token": tok},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 200
    out = r.json()
    assert out.get("ok") is False
