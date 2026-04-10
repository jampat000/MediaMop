"""Auth boundary integration tests — SQLite under ``MEDIAMOP_HOME`` (session autouse in conftest)."""

from __future__ import annotations

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from mediamop.api.factory import create_app
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.platform.activity import constants as activity_constants
from mediamop.platform.activity.models import ActivityEvent
from mediamop.platform.auth.models import User, UserRole
from mediamop.platform.auth.password import hash_password
from tests.integration_helpers import auth_post, csrf as fetch_csrf, reset_user_tables


def test_login_me_logout_flow(client_with_admin: TestClient) -> None:
    csrf = fetch_csrf(client_with_admin)
    r_login = auth_post(
        client_with_admin,
        "/api/v1/auth/login",
        json={
            "username": "alice",
            "password": "test-password-strong",
            "csrf_token": csrf,
        },
    )
    assert r_login.status_code == 200, r_login.text
    assert r_login.json()["user"]["username"] == "alice"
    cookie_name = MediaMopSettings.load().session_cookie_name
    cookie = client_with_admin.cookies.get(cookie_name)
    assert cookie is not None and len(cookie) > 20

    r_me = client_with_admin.get("/api/v1/auth/me")
    assert r_me.status_code == 200
    assert r_me.json()["user"]["username"] == "alice"

    csrf2 = fetch_csrf(client_with_admin)
    r_out = auth_post(
        client_with_admin,
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": csrf2},
    )
    assert r_out.status_code == 204, r_out.text

    r_me2 = client_with_admin.get("/api/v1/auth/me")
    assert r_me2.status_code == 401


def test_login_invalid_password(client_with_admin: TestClient) -> None:
    csrf = fetch_csrf(client_with_admin)
    r = auth_post(
        client_with_admin,
        "/api/v1/auth/login",
        json={
            "username": "alice",
            "password": "wrong-password",
            "csrf_token": csrf,
        },
    )
    assert r.status_code == 401


def test_login_failed_persisted_throttled_per_username(client_with_admin: TestClient) -> None:
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    with fac() as db:
        db.execute(
            delete(ActivityEvent).where(
                ActivityEvent.event_type == activity_constants.AUTH_LOGIN_FAILED,
                ActivityEvent.detail == "alice",
            ),
        )
        db.commit()
    with fac() as db:
        before = db.scalar(
            select(func.count()).select_from(ActivityEvent).where(
                ActivityEvent.event_type == activity_constants.AUTH_LOGIN_FAILED,
                ActivityEvent.detail == "alice",
            ),
        )
    for _ in range(3):
        tok = fetch_csrf(client_with_admin)
        r = auth_post(
            client_with_admin,
            "/api/v1/auth/login",
            json={
                "username": "alice",
                "password": "wrong-password",
                "csrf_token": tok,
            },
        )
        assert r.status_code == 401
    with fac() as db:
        after = db.scalar(
            select(func.count()).select_from(ActivityEvent).where(
                ActivityEvent.event_type == activity_constants.AUTH_LOGIN_FAILED,
                ActivityEvent.detail == "alice",
            ),
        )
    assert int(after or 0) - int(before or 0) == 1


def test_login_invalid_csrf(client_with_admin: TestClient) -> None:
    r = auth_post(
        client_with_admin,
        "/api/v1/auth/login",
        json={
            "username": "alice",
            "password": "test-password-strong",
            "csrf_token": "invalid-token",
        },
    )
    assert r.status_code == 400


def test_logout_rejects_missing_csrf(client_with_admin: TestClient) -> None:
    csrf = fetch_csrf(client_with_admin)
    auth_post(
        client_with_admin,
        "/api/v1/auth/login",
        json={
            "username": "alice",
            "password": "test-password-strong",
            "csrf_token": csrf,
        },
    )
    r = auth_post(client_with_admin, "/api/v1/auth/logout")
    assert r.status_code == 400


def test_session_rotation_replaces_old_cookie(client_with_admin: TestClient) -> None:
    csrf1 = fetch_csrf(client_with_admin)
    auth_post(
        client_with_admin,
        "/api/v1/auth/login",
        json={
            "username": "alice",
            "password": "test-password-strong",
            "csrf_token": csrf1,
        },
    )
    cookie_name = MediaMopSettings.load().session_cookie_name
    old_cookie = client_with_admin.cookies.get(cookie_name)
    csrf2 = fetch_csrf(client_with_admin)
    auth_post(
        client_with_admin,
        "/api/v1/auth/login",
        json={
            "username": "alice",
            "password": "test-password-strong",
            "csrf_token": csrf2,
        },
    )
    new_cookie = client_with_admin.cookies.get(cookie_name)
    assert old_cookie != new_cookie
    r_me = client_with_admin.get("/api/v1/auth/me")
    assert r_me.status_code == 200


def test_admin_ping_requires_admin(client_with_admin: TestClient) -> None:
    csrf = fetch_csrf(client_with_admin)
    auth_post(
        client_with_admin,
        "/api/v1/auth/login",
        json={
            "username": "alice",
            "password": "test-password-strong",
            "csrf_token": csrf,
        },
    )
    r = client_with_admin.get("/api/v1/auth/admin/ping")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_admin_ping_forbidden_for_viewer(client_with_viewer: TestClient) -> None:
    csrf = fetch_csrf(client_with_viewer)
    auth_post(
        client_with_viewer,
        "/api/v1/auth/login",
        json={
            "username": "bob",
            "password": "viewer-password-here",
            "csrf_token": csrf,
        },
    )
    r = client_with_viewer.get("/api/v1/auth/admin/ping")
    assert r.status_code == 403


def test_bootstrap_allowed_when_no_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_BOOTSTRAP_RATE_MAX_ATTEMPTS", "100")
    monkeypatch.setenv("MEDIAMOP_BOOTSTRAP_RATE_WINDOW_SECONDS", "60")
    reset_user_tables()
    app = create_app()
    with TestClient(app) as client:
        r_s = client.get("/api/v1/auth/bootstrap/status")
        assert r_s.status_code == 200
        assert r_s.json()["bootstrap_allowed"] is True
        csrf = fetch_csrf(client)
        r_b = auth_post(
            client,
            "/api/v1/auth/bootstrap",
            json={
                "username": "owner1",
                "password": "first-owner-pass-min8",
                "csrf_token": csrf,
            },
        )
        assert r_b.status_code == 200, r_b.text
        assert r_b.json()["username"] == "owner1"
        r_s2 = client.get("/api/v1/auth/bootstrap/status")
        assert r_s2.json()["bootstrap_allowed"] is False
        csrf2 = fetch_csrf(client)
        r_login = auth_post(
            client,
            "/api/v1/auth/login",
            json={
                "username": "owner1",
                "password": "first-owner-pass-min8",
                "csrf_token": csrf2,
            },
        )
        assert r_login.status_code == 200, r_login.text
        r_act = client.get("/api/v1/activity/recent")
        assert r_act.status_code == 200, r_act.text
        et = {x["event_type"] for x in r_act.json()["items"]}
        assert "auth.bootstrap_succeeded" in et
        assert "auth.login_succeeded" in et


def test_bootstrap_username_conflict_returns_409() -> None:
    reset_user_tables()
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    with fac() as db:
        db.add(
            User(
                username="taken",
                password_hash=hash_password("irrelevant-password-here"),
                role=UserRole.viewer.value,
                is_active=True,
            )
        )
        db.commit()
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/api/v1/auth/bootstrap/status").json()["bootstrap_allowed"] is True
        csrf = fetch_csrf(client)
        r = auth_post(
            client,
            "/api/v1/auth/bootstrap",
            json={
                "username": "taken",
                "password": "valid-pass-bootstrap-8",
                "csrf_token": csrf,
            },
        )
        assert r.status_code == 409


def test_bootstrap_blocked_after_admin_exists(client_with_admin: TestClient) -> None:
    r_s = client_with_admin.get("/api/v1/auth/bootstrap/status")
    assert r_s.json()["bootstrap_allowed"] is False
    csrf = fetch_csrf(client_with_admin)
    r_b = auth_post(
        client_with_admin,
        "/api/v1/auth/bootstrap",
        json={
            "username": "intruder",
            "password": "some-long-password-here",
            "csrf_token": csrf,
        },
    )
    assert r_b.status_code == 403


def test_bootstrap_denied_persisted_throttled(client_with_admin: TestClient) -> None:
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    with fac() as db:
        db.execute(
            delete(ActivityEvent).where(
                ActivityEvent.event_type == activity_constants.AUTH_BOOTSTRAP_DENIED,
            ),
        )
        db.commit()
    with fac() as db:
        before = db.scalar(
            select(func.count()).select_from(ActivityEvent).where(
                ActivityEvent.event_type == activity_constants.AUTH_BOOTSTRAP_DENIED,
            ),
        )
    tok = fetch_csrf(client_with_admin)
    r1 = auth_post(
        client_with_admin,
        "/api/v1/auth/bootstrap",
        json={
            "username": "intruder",
            "password": "some-long-password-here",
            "csrf_token": tok,
        },
    )
    assert r1.status_code == 403
    tok2 = fetch_csrf(client_with_admin)
    r2 = auth_post(
        client_with_admin,
        "/api/v1/auth/bootstrap",
        json={
            "username": "intruder2",
            "password": "other-long-password-here",
            "csrf_token": tok2,
        },
    )
    assert r2.status_code == 403
    with fac() as db:
        after = db.scalar(
            select(func.count()).select_from(ActivityEvent).where(
                ActivityEvent.event_type == activity_constants.AUTH_BOOTSTRAP_DENIED,
            ),
        )
    assert int(after or 0) - int(before or 0) == 1


def test_login_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_AUTH_LOGIN_RATE_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("MEDIAMOP_AUTH_LOGIN_RATE_WINDOW_SECONDS", "120")
    reset_user_tables()
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    with fac() as db:
        db.add(
            User(
                username="alice",
                password_hash=hash_password("test-password-strong"),
                role="admin",
                is_active=True,
            )
        )
        db.commit()
    app = create_app()
    with TestClient(app) as client:
        for i in range(3):
            csrf = fetch_csrf(client)
            r = auth_post(
                client,
                "/api/v1/auth/login",
                json={
                    "username": "alice",
                    "password": "wrong",
                    "csrf_token": csrf,
                },
            )
            assert r.status_code == 401, r.text
        csrf_last = fetch_csrf(client)
        r_limit = auth_post(
            client,
            "/api/v1/auth/login",
            json={
                "username": "alice",
                "password": "wrong",
                "csrf_token": csrf_last,
            },
        )
        assert r_limit.status_code == 429
        assert "Retry-After" in r_limit.headers


def test_activity_recent_requires_authentication(client_with_admin: TestClient) -> None:
    r = client_with_admin.get("/api/v1/activity/recent")
    assert r.status_code == 401


def test_activity_recent_includes_login_event(client_with_admin: TestClient) -> None:
    csrf = fetch_csrf(client_with_admin)
    r_login = auth_post(
        client_with_admin,
        "/api/v1/auth/login",
        json={
            "username": "alice",
            "password": "test-password-strong",
            "csrf_token": csrf,
        },
    )
    assert r_login.status_code == 200, r_login.text
    r_act = client_with_admin.get("/api/v1/activity/recent")
    assert r_act.status_code == 200, r_act.text
    items = r_act.json()["items"]
    assert any(
        x.get("event_type") == "auth.login_succeeded" and x.get("detail") == "alice" for x in items
    )


def test_activity_recent_includes_logout_event(client_with_admin: TestClient) -> None:
    csrf = fetch_csrf(client_with_admin)
    auth_post(
        client_with_admin,
        "/api/v1/auth/login",
        json={
            "username": "alice",
            "password": "test-password-strong",
            "csrf_token": csrf,
        },
    )
    csrf2 = fetch_csrf(client_with_admin)
    r_out = auth_post(
        client_with_admin,
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": csrf2},
    )
    assert r_out.status_code == 204, r_out.text
    csrf3 = fetch_csrf(client_with_admin)
    auth_post(
        client_with_admin,
        "/api/v1/auth/login",
        json={
            "username": "alice",
            "password": "test-password-strong",
            "csrf_token": csrf3,
        },
    )
    r_act = client_with_admin.get("/api/v1/activity/recent")
    assert r_act.status_code == 200
    items = r_act.json()["items"]
    types_in_order = [x["event_type"] for x in items[:3]]
    assert "auth.login_succeeded" in types_in_order
    assert "auth.logout" in types_in_order


def test_security_headers_on_health_and_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_SECURITY_ENABLE_HSTS", "1")
    reset_user_tables()
    app = create_app()
    with TestClient(app) as client:
        r_h = client.get("/health")
        assert r_h.headers.get("X-Content-Type-Options") == "nosniff"
        assert r_h.headers.get("strict-transport-security")
        r_csrf = client.get("/api/v1/auth/csrf")
        assert r_csrf.headers.get("Content-Security-Policy")
        assert "frame-ancestors" in (r_csrf.headers.get("Content-Security-Policy") or "").lower()
        assert r_csrf.headers.get("Cache-Control", "").startswith("no-store")
