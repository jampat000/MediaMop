"""Auth boundary integration tests — SQLite under ``MEDIAMOP_HOME`` (session autouse in conftest)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from mediamop.api.factory import create_app
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import create_db_engine, create_session_factory
from mediamop.platform.activity import constants as activity_constants
from mediamop.platform.activity.models import ActivityEvent
from mediamop.platform.auth import service as auth_service
from mediamop.platform.auth.models import User, UserRole, UserSession
from mediamop.platform.auth.password import hash_password
from mediamop.platform.auth.sessions import revoke_session
from mediamop.core.datetime_util import as_utc
from tests.integration_helpers import auth_post, csrf as fetch_csrf, reset_user_tables, seed_admin_user


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
    r_session = client_with_admin.get("/api/v1/auth/session")
    assert r_session.status_code == 200
    assert r_session.json()["trusted_device"] is False

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


def test_change_password_requires_current_and_forces_new_login(client_with_admin: TestClient) -> None:
    csrf = fetch_csrf(client_with_admin)
    r_login = auth_post(
        client_with_admin,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": csrf},
    )
    assert r_login.status_code == 200, r_login.text
    csrf2 = fetch_csrf(client_with_admin)
    r_change = auth_post(
        client_with_admin,
        "/api/v1/auth/change-password",
        json={
            "csrf_token": csrf2,
            "current_password": "test-password-strong",
            "new_password": "new-password-stronger-123",
        },
    )
    assert r_change.status_code == 200, r_change.text
    assert "sign in again" in r_change.json()["message"].lower()
    r_me = client_with_admin.get("/api/v1/auth/me")
    assert r_me.status_code == 401
    csrf3 = fetch_csrf(client_with_admin)
    r_old = auth_post(
        client_with_admin,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": csrf3},
    )
    assert r_old.status_code == 401
    csrf4 = fetch_csrf(client_with_admin)
    r_new = auth_post(
        client_with_admin,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "new-password-stronger-123", "csrf_token": csrf4},
    )
    assert r_new.status_code == 200, r_new.text


def test_change_password_rejects_wrong_current_password(client_with_admin: TestClient) -> None:
    csrf = fetch_csrf(client_with_admin)
    r_login = auth_post(
        client_with_admin,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": csrf},
    )
    assert r_login.status_code == 200, r_login.text
    csrf2 = fetch_csrf(client_with_admin)
    r_change = auth_post(
        client_with_admin,
        "/api/v1/auth/change-password",
        json={
            "csrf_token": csrf2,
            "current_password": "wrong-current-password",
            "new_password": "new-password-stronger-123",
        },
    )
    assert r_change.status_code == 400
    assert "current password" in (r_change.json().get("detail") or "").lower()


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


def test_login_cookie_has_explicit_lifetime(client_with_admin: TestClient) -> None:
    csrf = fetch_csrf(client_with_admin)
    response = auth_post(
        client_with_admin,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": csrf},
    )

    assert response.status_code == 200, response.text
    set_cookie = response.headers.get("set-cookie", "")
    assert "Max-Age=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=" in set_cookie


def test_trusted_device_login_uses_extended_session_policy(client_with_admin: TestClient) -> None:
    csrf = fetch_csrf(client_with_admin)
    response = auth_post(
        client_with_admin,
        "/api/v1/auth/login",
        json={
            "username": "alice",
            "password": "test-password-strong",
            "csrf_token": csrf,
            "trusted_device": True,
        },
    )
    assert response.status_code == 200, response.text

    session_response = client_with_admin.get("/api/v1/auth/session")
    assert session_response.status_code == 200, session_response.text
    body = session_response.json()
    assert body["trusted_device"] is True
    assert body["idle_timeout_minutes"] == 60 * 1440
    assert body["absolute_timeout_days"] == 365

    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    with fac() as db:
        row = db.scalars(select(UserSession).order_by(UserSession.created_at.desc())).first()
        assert row is not None
        assert row.is_trusted_device is True


def test_session_cookie_survives_backend_app_restart() -> None:
    seed_admin_user()
    cookie_name = MediaMopSettings.load().session_cookie_name
    app1 = create_app()
    with TestClient(app1) as client1:
        csrf = fetch_csrf(client1)
        login = auth_post(
            client1,
            "/api/v1/auth/login",
            json={"username": "alice", "password": "test-password-strong", "csrf_token": csrf},
        )
        assert login.status_code == 200, login.text
        cookie = client1.cookies.get(cookie_name)
        assert cookie

    app2 = create_app()
    with TestClient(app2) as client2:
        client2.cookies.set(cookie_name, cookie, path="/")
        me = client2.get("/api/v1/auth/me")
        assert me.status_code == 200, me.text
        assert me.json()["user"]["username"] == "alice"


def test_second_browser_login_does_not_revoke_first_browser_session() -> None:
    seed_admin_user()
    app = create_app()
    with TestClient(app) as remote_client, TestClient(app) as local_client:
        remote_csrf = fetch_csrf(remote_client)
        remote_login = auth_post(
            remote_client,
            "/api/v1/auth/login",
            json={
                "username": "alice",
                "password": "test-password-strong",
                "csrf_token": remote_csrf,
            },
        )
        assert remote_login.status_code == 200, remote_login.text
        assert remote_client.get("/api/v1/auth/me").status_code == 200

        local_csrf = fetch_csrf(local_client)
        local_login = auth_post(
            local_client,
            "/api/v1/auth/login",
            json={
                "username": "alice",
                "password": "test-password-strong",
                "csrf_token": local_csrf,
            },
        )
        assert local_login.status_code == 200, local_login.text
        assert local_client.get("/api/v1/auth/me").status_code == 200
        assert remote_client.get("/api/v1/auth/me").status_code == 200


def test_authenticated_csrf_token_is_rejected_across_sessions() -> None:
    seed_admin_user()
    app = create_app()
    with TestClient(app) as client_a, TestClient(app) as client_b:
        csrf_a_login = fetch_csrf(client_a)
        login_a = auth_post(
            client_a,
            "/api/v1/auth/login",
            json={"username": "alice", "password": "test-password-strong", "csrf_token": csrf_a_login},
        )
        assert login_a.status_code == 200, login_a.text

        csrf_b_login = fetch_csrf(client_b)
        login_b = auth_post(
            client_b,
            "/api/v1/auth/login",
            json={"username": "alice", "password": "test-password-strong", "csrf_token": csrf_b_login},
        )
        assert login_b.status_code == 200, login_b.text

        session_a_csrf = fetch_csrf(client_a)
        cross_session = auth_post(
            client_b,
            "/api/v1/auth/change-password",
            json={
                "csrf_token": session_a_csrf,
                "current_password": "test-password-strong",
                "new_password": "new-password-stronger-123",
            },
        )
        assert cross_session.status_code == 400


def test_login_keeps_only_newest_five_active_sessions() -> None:
    seed_admin_user()
    settings = MediaMopSettings.load()
    app = create_app()
    clients = [TestClient(app) for _ in range(6)]
    with clients[0], clients[1], clients[2], clients[3], clients[4], clients[5]:
        for client in clients:
            csrf = fetch_csrf(client)
            login = auth_post(
                client,
                "/api/v1/auth/login",
                json={"username": "alice", "password": "test-password-strong", "csrf_token": csrf},
            )
            assert login.status_code == 200, login.text

        assert clients[0].get("/api/v1/auth/me").status_code == 401
        for client in clients[1:]:
            assert client.get("/api/v1/auth/me").status_code == 200

    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    with fac() as db:
        active = db.scalars(select(UserSession).where(UserSession.revoked_at.is_(None))).all()
        revoked = db.scalars(select(UserSession).where(UserSession.revoked_at.is_not(None))).all()
    assert len(active) == 5
    assert len(revoked) == 1


def test_session_limit_ignores_absolute_expired_sessions() -> None:
    seed_admin_user()
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    base = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    with patch("mediamop.platform.auth.service.utcnow", return_value=base):
        with fac() as db:
            user = db.scalars(select(User).where(User.username == "alice")).one()
            for _ in range(5):
                row, _raw = auth_service.create_user_session(db, user, settings=settings)
                row.absolute_expires_at = base - timedelta(seconds=1)
            live, _raw = auth_service.create_user_session(db, user, settings=settings)
            db.commit()

    with fac() as db:
        live_row = db.get(UserSession, live.id)
        expired_rows = db.scalars(select(UserSession).where(UserSession.id != live.id)).all()

    assert live_row is not None
    assert live_row.revoked_at is None
    assert all(row.revoked_at is None for row in expired_rows)


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


def test_bootstrap_rejects_short_password() -> None:
    reset_user_tables()
    app = create_app()
    with TestClient(app) as client:
        assert client.get("/api/v1/auth/bootstrap/status").json()["bootstrap_allowed"] is True
        csrf = fetch_csrf(client)
        r = auth_post(
            client,
            "/api/v1/auth/bootstrap",
            json={
                "username": "owner1",
                "password": "short",
                "csrf_token": csrf,
            },
        )
        assert r.status_code == 422, r.text
        detail = r.json().get("detail") or []
        assert any(
            item.get("loc") == ["body", "password"] and "at least 12 characters" in item.get("msg", "")
            for item in detail
            if isinstance(item, dict)
        )


def test_bootstrap_rejects_common_password() -> None:
    reset_user_tables()
    app = create_app()
    with TestClient(app) as client:
        csrf = fetch_csrf(client)
        r = auth_post(
            client,
            "/api/v1/auth/bootstrap",
            json={
                "username": "owner1",
                "password": "password1234",
                "csrf_token": csrf,
            },
        )
        assert r.status_code == 400, r.text
        assert "common" in r.json()["detail"].lower()


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
    # Ordering can tie on identical timestamps (SQLite); require presence in the page, not top-3.
    types = [x["event_type"] for x in items]
    assert "auth.login_succeeded" in types
    assert "auth.logout" in types


def test_load_valid_session_throttles_last_seen_persistence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid persisting last_seen on every authenticated read (SQLite write pressure)."""

    # Touch gap is min(60s, idle/2); a low MEDIAMOP_SESSION_IDLE_MINUTES in .env/CI would
    # shrink the gap and make +30s persist last_seen, breaking the assertions below.
    monkeypatch.setenv("MEDIAMOP_SESSION_IDLE_MINUTES", "720")
    seed_admin_user()
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    base = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    sid: int
    raw: str
    with patch("mediamop.platform.auth.service.utcnow", return_value=base):
        with fac() as db:
            user = db.scalars(select(User).where(User.username == "alice")).one()
            row, raw = auth_service.create_user_session(db, user, settings=settings)
            sid = row.id
            db.commit()

    def read_last_seen() -> datetime:
        with fac() as db:
            r = db.get(UserSession, sid)
            assert r is not None
            return as_utc(r.last_seen_at)

    assert read_last_seen() == base

    with patch(
        "mediamop.platform.auth.service.utcnow",
        return_value=base + timedelta(seconds=30),
    ):
        with fac() as db:
            pair = auth_service.load_valid_session_for_request(db, raw, settings)
            assert pair is not None
            db.commit()

    assert read_last_seen() == base

    later = base + timedelta(seconds=61)
    with patch("mediamop.platform.auth.service.utcnow", return_value=later):
        with fac() as db:
            pair = auth_service.load_valid_session_for_request(db, raw, settings)
            assert pair is not None
            db.commit()

    assert read_last_seen() == later


def test_expired_session_is_rejected_and_revoked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_SESSION_IDLE_MINUTES", "720")
    seed_admin_user()
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    base = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

    with patch("mediamop.platform.auth.service.utcnow", return_value=base):
        with fac() as db:
            user = db.scalars(select(User).where(User.username == "alice")).one()
            row, raw = auth_service.create_user_session(db, user, settings=settings)
            sid = row.id
            db.commit()

    with patch("mediamop.platform.auth.service.utcnow", return_value=base + timedelta(days=settings.session_absolute_days + 1)):
        with fac() as db:
            pair = auth_service.load_valid_session_for_request(db, raw, settings)
            db.commit()

    assert pair is None
    with fac() as db:
        row = db.get(UserSession, sid)
        assert row is not None
        assert row.revoked_at is not None


def test_session_cleanup_deletes_revoked_and_expired_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_SESSION_IDLE_MINUTES", "720")
    seed_admin_user()
    settings = MediaMopSettings.load()
    eng = create_db_engine(settings)
    fac = create_session_factory(eng)
    base = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

    with patch("mediamop.platform.auth.service.utcnow", return_value=base):
        with fac() as db:
            user = db.scalars(select(User).where(User.username == "alice")).one()
            revoked, _ = auth_service.create_user_session(db, user, settings=settings)
            expired, _ = auth_service.create_user_session(db, user, settings=settings)
            active, _ = auth_service.create_user_session(db, user, settings=settings)
            revoke_session(revoked, at=base)
            expired.absolute_expires_at = base - timedelta(seconds=1)
            db.commit()

    with fac() as db:
        removed = auth_service.cleanup_inactive_sessions(db, settings=settings, now=base)
        db.commit()

    assert removed == 2
    with fac() as db:
        rows = db.scalars(select(UserSession)).all()
    assert [row.id for row in rows] == [active.id]


def test_security_headers_on_health_and_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_SECURITY_ENABLE_HSTS", "1")
    reset_user_tables()
    app = create_app()
    with TestClient(app) as client:
        r_h = client.get("/health")
        assert r_h.headers.get("X-Content-Type-Options") == "nosniff"
        assert r_h.headers.get("X-Frame-Options") == "DENY"
        assert r_h.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert r_h.headers.get("Content-Security-Policy")
        assert r_h.headers.get("Cache-Control", "").startswith("no-store")
        assert r_h.headers.get("strict-transport-security")
        r_csrf = client.get("/api/v1/auth/csrf")
        assert r_csrf.headers.get("Content-Security-Policy")
        assert "frame-ancestors" in (r_csrf.headers.get("Content-Security-Policy") or "").lower()
        assert r_csrf.headers.get("Cache-Control", "").startswith("no-store")
        r_system = client.get("/api/v1/system/directories")
        assert r_system.headers.get("Cache-Control", "").startswith("no-store")
        r_metrics = client.get("/metrics")
        assert r_metrics.headers.get("Cache-Control", "").startswith("no-store")


def test_static_assets_do_not_get_api_no_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dist = tmp_path / "web"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<div id='root'></div>", encoding="utf-8")
    (assets / "app.js").write_text("console.log('ok');", encoding="utf-8")
    monkeypatch.setenv("MEDIAMOP_WEB_DIST", str(dist))

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/assets/app.js")

    assert response.status_code == 200
    assert response.headers.get("Cache-Control") != "no-store, private"


def test_bundled_html_csp_does_not_allow_inline_styles(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dist = tmp_path / "web"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id='root'></div>", encoding="utf-8")
    monkeypatch.setenv("MEDIAMOP_WEB_DIST", str(dist))

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    csp = response.headers.get("Content-Security-Policy") or ""
    assert "style-src 'self'" in csp
    assert "fonts.googleapis.com" not in csp
    assert "fonts.gstatic.com" not in csp
    assert "'unsafe-inline'" not in csp


def test_spa_login_route_serves_index_html(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dist = tmp_path / "web"
    dist.mkdir(parents=True)
    html = "<!doctype html><html><body><div id='root'>MediaMop</div></body></html>"
    (dist / "index.html").write_text(html, encoding="utf-8")
    monkeypatch.setenv("MEDIAMOP_WEB_DIST", str(dist))

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/login?session=expired", headers={"Accept": "text/html"})

    assert response.status_code == 200
    assert "text/html" in (response.headers.get("content-type") or "").lower()
    assert "MediaMop" in response.text


def test_missing_static_asset_still_returns_404(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dist = tmp_path / "web"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id='root'></div>", encoding="utf-8")
    monkeypatch.setenv("MEDIAMOP_WEB_DIST", str(dist))

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/assets/missing.js", headers={"Accept": "*/*"})

    assert response.status_code == 404
