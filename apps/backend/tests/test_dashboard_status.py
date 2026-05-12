"""Dashboard JSON — service composition and authenticated route (SQLite)."""

from __future__ import annotations

from starlette.testclient import TestClient

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.modules.dashboard.service import build_dashboard_status
from tests.integration_helpers import auth_post
from tests.integration_helpers import csrf as fetch_csrf


def _session_factory():
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    return settings, fac


def test_build_dashboard_status() -> None:
    settings, fac = _session_factory()
    with fac() as db:
        out = build_dashboard_status(db, settings)
        db.commit()
    assert out.system.healthy is True
    assert isinstance(out.activity_summary.events_last_24h, int)
    assert out.activity_summary.latest is None or out.activity_summary.latest.id > 0


def test_get_dashboard_status_authenticated(client_with_admin: TestClient) -> None:
    tok = fetch_csrf(client_with_admin)
    r_login = auth_post(
        client_with_admin,
        "/api/v1/auth/login",
        json={
            "username": "alice",
            "password": "test-password-strong",
            "csrf_token": tok,
        },
    )
    assert r_login.status_code == 200, r_login.text
    r = client_with_admin.get("/api/v1/dashboard/status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scope_note"]
    assert body["system"]["healthy"] is True
    assert "api_version" in body["system"]
    summ = body["activity_summary"]
    assert "events_last_24h" in summ
    assert "latest" in summ
