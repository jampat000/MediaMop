"""Auth boundary integration tests — require PostgreSQL (see CI ``services: postgres``)."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from mediamop.api.factory import create_app
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.platform.auth.models import User, UserSession, UserRole
from mediamop.platform.auth.password import hash_password

pytestmark = pytest.mark.skipif(
    not os.environ.get("MEDIAMOP_DATABASE_URL"),
    reason="Set MEDIAMOP_DATABASE_URL to run auth integration tests.",
)


@pytest.fixture(autouse=True)
def ensure_session_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "MEDIAMOP_SESSION_SECRET",
        os.environ.get("MEDIAMOP_SESSION_SECRET", "pytest-session-secret-32-chars-min!!"),
    )


def _reset_tables() -> None:
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    with fac() as db:
        assert isinstance(db, Session)
        db.execute(delete(UserSession))
        db.execute(delete(User))
        db.commit()


@pytest.fixture
def client_with_admin() -> TestClient:
    _reset_tables()
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
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_with_viewer() -> TestClient:
    _reset_tables()
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    with fac() as db:
        db.add(
            User(
                username="bob",
                password_hash=hash_password("viewer-password-here"),
                role=UserRole.viewer.value,
                is_active=True,
            )
        )
        db.commit()
    app = create_app()
    with TestClient(app) as c:
        yield c


def _csrf(client: TestClient) -> str:
    r = client.get("/api/v1/auth/csrf")
    assert r.status_code == 200, r.text
    return r.json()["csrf_token"]


def _trusted_browser_origin_headers() -> dict[str, str]:
    """Unsafe auth POSTs require Origin/Referer when trusted origins are configured (typical .env)."""

    settings = MediaMopSettings.load()
    trusted = settings.trusted_browser_origins
    if not trusted:
        return {}
    return {"Origin": trusted[0].rstrip("/")}


def _auth_post(
    client: TestClient,
    path: str,
    *,
    json: dict | None = None,
    headers: dict[str, str] | None = None,
):
    merged = {**_trusted_browser_origin_headers(), **(headers or {})}
    kw: dict[str, object] = {"headers": merged}
    if json is not None:
        kw["json"] = json
    return client.post(path, **kw)


def test_login_me_logout_flow(client_with_admin: TestClient) -> None:
    csrf = _csrf(client_with_admin)
    r_login = _auth_post(
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

    csrf2 = _csrf(client_with_admin)
    r_out = _auth_post(
        client_with_admin,
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": csrf2},
    )
    assert r_out.status_code == 204, r_out.text

    r_me2 = client_with_admin.get("/api/v1/auth/me")
    assert r_me2.status_code == 401


def test_login_invalid_password(client_with_admin: TestClient) -> None:
    csrf = _csrf(client_with_admin)
    r = _auth_post(
        client_with_admin,
        "/api/v1/auth/login",
        json={
            "username": "alice",
            "password": "wrong-password",
            "csrf_token": csrf,
        },
    )
    assert r.status_code == 401


def test_login_invalid_csrf(client_with_admin: TestClient) -> None:
    r = _auth_post(
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
    csrf = _csrf(client_with_admin)
    _auth_post(
        client_with_admin,
        "/api/v1/auth/login",
        json={
            "username": "alice",
            "password": "test-password-strong",
            "csrf_token": csrf,
        },
    )
    r = _auth_post(client_with_admin, "/api/v1/auth/logout")
    assert r.status_code == 400


def test_session_rotation_replaces_old_cookie(client_with_admin: TestClient) -> None:
    csrf1 = _csrf(client_with_admin)
    _auth_post(
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
    csrf2 = _csrf(client_with_admin)
    _auth_post(
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
    csrf = _csrf(client_with_admin)
    _auth_post(
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
    csrf = _csrf(client_with_viewer)
    _auth_post(
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
    _reset_tables()
    app = create_app()
    with TestClient(app) as client:
        r_s = client.get("/api/v1/auth/bootstrap/status")
        assert r_s.status_code == 200
        assert r_s.json()["bootstrap_allowed"] is True
        csrf = _csrf(client)
        r_b = _auth_post(
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


def test_bootstrap_username_conflict_returns_409() -> None:
    _reset_tables()
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
        csrf = _csrf(client)
        r = _auth_post(
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
    csrf = _csrf(client_with_admin)
    r_b = _auth_post(
        client_with_admin,
        "/api/v1/auth/bootstrap",
        json={
            "username": "intruder",
            "password": "some-long-password-here",
            "csrf_token": csrf,
        },
    )
    assert r_b.status_code == 403


def test_login_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_AUTH_LOGIN_RATE_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("MEDIAMOP_AUTH_LOGIN_RATE_WINDOW_SECONDS", "120")
    _reset_tables()
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
            csrf = _csrf(client)
            r = _auth_post(
                client,
                "/api/v1/auth/login",
                json={
                    "username": "alice",
                    "password": "wrong",
                    "csrf_token": csrf,
                },
            )
            assert r.status_code == 401, r.text
        csrf_last = _csrf(client)
        r_limit = _auth_post(
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


def test_security_headers_on_health_and_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_SECURITY_ENABLE_HSTS", "1")
    _reset_tables()
    app = create_app()
    with TestClient(app) as client:
        r_h = client.get("/health")
        assert r_h.headers.get("X-Content-Type-Options") == "nosniff"
        assert r_h.headers.get("strict-transport-security")
        r_csrf = client.get("/api/v1/auth/csrf")
        assert r_csrf.headers.get("Content-Security-Policy")
        assert "frame-ancestors" in (r_csrf.headers.get("Content-Security-Policy") or "").lower()
        assert r_csrf.headers.get("Cache-Control", "").startswith("no-store")
