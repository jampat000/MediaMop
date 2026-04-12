"""GET/PUT ``/api/v1/suite/settings`` and GET ``/api/v1/suite/security-overview``."""

from __future__ import annotations

from sqlalchemy import select
from starlette.testclient import TestClient

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.platform.suite_settings.model import SuiteSettingsRow
from mediamop.platform.suite_settings.service import apply_suite_settings_put

from tests.integration_helpers import auth_post, csrf as fetch_csrf, trusted_browser_origin_headers


def _login_admin(client: TestClient) -> None:
    tok = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


def test_suite_settings_get_requires_auth(client_with_admin: TestClient) -> None:
    r = client_with_admin.get("/api/v1/suite/settings")
    assert r.status_code == 401


def test_suite_settings_get_ok_for_viewer(client_with_viewer: TestClient) -> None:
    tok = fetch_csrf(client_with_viewer)
    r_login = auth_post(
        client_with_viewer,
        "/api/v1/auth/login",
        json={"username": "bob", "password": "viewer-password-here", "csrf_token": tok},
    )
    assert r_login.status_code == 200, r_login.text
    r = client_with_viewer.get("/api/v1/suite/settings")
    assert r.status_code == 200, r.text
    assert r.json()["product_display_name"] == "MediaMop"


def test_suite_settings_get_default_shape(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    r = client_with_admin.get("/api/v1/suite/settings")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["product_display_name"] == "MediaMop"
    assert body["signed_in_home_notice"] is None
    assert "updated_at" in body


def test_suite_security_overview_get_ok(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    r = client_with_admin.get("/api/v1/suite/security-overview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "restart_required_note" in body
    assert "session_signing_configured" in body
    assert "allowed_browser_origins_count" in body


def test_suite_settings_put_persists(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r = client_with_admin.put(
        "/api/v1/suite/settings",
        json={
            "csrf_token": tok,
            "product_display_name": "House Library",
            "signed_in_home_notice": "Welcome back.",
        },
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["product_display_name"] == "House Library"
    assert r.json()["signed_in_home_notice"] == "Welcome back."

    r2 = client_with_admin.get("/api/v1/suite/settings")
    assert r2.status_code == 200
    assert r2.json()["product_display_name"] == "House Library"

    settings = MediaMopSettings.load()
    fac = create_session_factory(create_db_engine(settings))
    with fac() as db:
        row = db.scalars(select(SuiteSettingsRow).where(SuiteSettingsRow.id == 1)).one()
        assert row.product_display_name == "House Library"


def test_suite_settings_put_viewer_forbidden(client_with_viewer: TestClient) -> None:
    tok = fetch_csrf(client_with_viewer)
    r_login = auth_post(
        client_with_viewer,
        "/api/v1/auth/login",
        json={"username": "bob", "password": "viewer-password-here", "csrf_token": tok},
    )
    assert r_login.status_code == 200, r_login.text
    tok2 = fetch_csrf(client_with_viewer)
    r = client_with_viewer.put(
        "/api/v1/suite/settings",
        json={"csrf_token": tok2, "product_display_name": "X", "signed_in_home_notice": None},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 403


def test_apply_suite_settings_put_rejects_blank_name() -> None:
    settings = MediaMopSettings.load()
    fac = create_session_factory(create_db_engine(settings))
    with fac() as db:
        try:
            apply_suite_settings_put(db, product_display_name="   ", signed_in_home_notice=None)
        except ValueError as exc:
            assert "empty" in str(exc).lower()
        else:
            raise AssertionError("expected ValueError")
