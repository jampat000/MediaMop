"""Contract port of apps/backend/tests/test_auth_api.py."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from tests.contract.auth import _helpers as h
from tests.contract.support import seed
from tests.contract.support.client import ADMIN_PASSWORD, ADMIN_USERNAME, API, WeirClient
from tests.contract.support.launcher import ServerUnderTest

NEW_PASSWORD = "new-password-stronger-123"


@pytest.fixture
def alice(client: WeirClient) -> WeirClient:
    """Anonymous client on a server where the admin ``alice`` exists (like ``client_with_admin``)."""

    h.ensure_admin_account(client)
    return client


@pytest.fixture(scope="module")
def viewer_seeded(server: ServerUnderTest) -> None:
    h.ensure_viewer(server)


def test_login_me_logout_flow(alice: WeirClient) -> None:
    r_login = h.post_login(alice)
    assert r_login.status_code == 200, r_login.text
    assert r_login.json()["user"]["username"] == "alice"
    cookie = alice.cookies.get(h.SESSION_COOKIE)
    assert cookie is not None and len(cookie) > 20

    r_me = alice.get(f"{API}/auth/me")
    assert r_me.status_code == 200
    assert r_me.json()["user"]["username"] == "alice"
    r_session = alice.get(f"{API}/auth/session")
    assert r_session.status_code == 200
    assert r_session.json()["trusted_device"] is False

    r_out = alice.post(f"{API}/auth/logout", headers={"X-CSRF-Token": alice.csrf()})
    assert r_out.status_code == 204, r_out.text

    assert alice.get(f"{API}/auth/me").status_code == 401


def test_login_invalid_password(alice: WeirClient) -> None:
    assert h.post_login(alice, password="wrong-password").status_code == 401


def test_login_rejects_unexpected_fields(alice: WeirClient) -> None:
    r = h.post_login(alice, unexpected="value")
    assert r.status_code == 422


def test_change_password_requires_current_and_forces_new_login(server_factory, client_factory) -> None:
    sut = server_factory()
    c = client_factory(sut)
    h.ensure_admin_account(c)
    assert h.post_login(c).status_code == 200
    r_change = c.post_csrf(
        f"{API}/auth/change-password",
        {"current_password": ADMIN_PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert r_change.status_code == 200, r_change.text
    assert "sign in again" in r_change.json()["message"].lower()
    assert c.get(f"{API}/auth/me").status_code == 401
    assert h.post_login(c).status_code == 401
    r_new = h.post_login(c, password=NEW_PASSWORD)
    assert r_new.status_code == 200, r_new.text


def test_change_password_rejects_wrong_current_password(alice: WeirClient) -> None:
    assert h.post_login(alice).status_code == 200
    r_change = alice.post_csrf(
        f"{API}/auth/change-password",
        {"current_password": "wrong-current-password", "new_password": NEW_PASSWORD},
    )
    assert r_change.status_code == 400
    assert "current password" in (r_change.json().get("detail") or "").lower()


def _count_events(conn, event_type: str, detail: str | None = None) -> int:
    if detail is None:
        return int(seed.scalar(conn, "SELECT COUNT(*) FROM activity_events WHERE event_type = ?", (event_type,)))
    return int(
        seed.scalar(
            conn,
            "SELECT COUNT(*) FROM activity_events WHERE event_type = ? AND detail = ?",
            (event_type, detail),
        )
    )


def test_login_failed_persisted_throttled_per_username(
    server: ServerUnderTest, alice: WeirClient, client_factory
) -> None:
    with seed.stopped(server) as conn:
        conn.execute("DELETE FROM activity_events WHERE event_type = 'auth.login_failed' AND detail = 'alice'")
        before = _count_events(conn, "auth.login_failed", "alice")
    c = client_factory(server)
    for _ in range(3):
        assert h.post_login(c, password="wrong-password").status_code == 401
    with seed.stopped(server) as conn:
        after = _count_events(conn, "auth.login_failed", "alice")
    assert after - before == 1


def test_login_invalid_csrf(alice: WeirClient) -> None:
    r = alice.post(
        f"{API}/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD, "csrf_token": "invalid-token"},
    )
    assert r.status_code == 400


def test_logout_rejects_missing_csrf(alice: WeirClient) -> None:
    h.post_login(alice)
    r = alice.post(f"{API}/auth/logout")
    assert r.status_code == 400


def test_session_rotation_replaces_old_cookie(alice: WeirClient) -> None:
    h.post_login(alice)
    old_cookie = alice.cookies.get(h.SESSION_COOKIE)
    h.post_login(alice)
    new_cookie = alice.cookies.get(h.SESSION_COOKIE)
    assert old_cookie != new_cookie
    assert alice.get(f"{API}/auth/me").status_code == 200


def test_login_cookie_has_explicit_lifetime(alice: WeirClient) -> None:
    response = h.post_login(alice)
    assert response.status_code == 200, response.text
    set_cookie = h.set_cookie_header(response)
    assert "Max-Age=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=" in set_cookie


def test_trusted_device_login_uses_extended_session_policy(
    server: ServerUnderTest, alice: WeirClient, client_factory
) -> None:
    response = h.post_login(alice, trusted_device=True)
    assert response.status_code == 200, response.text

    session_response = alice.get(f"{API}/auth/session")
    assert session_response.status_code == 200, session_response.text
    body = session_response.json()
    assert body["trusted_device"] is True
    assert body["idle_timeout_minutes"] == 60 * 1440
    assert body["absolute_timeout_days"] == 365
    session_id = body["session_id"]

    with seed.stopped(server) as conn:
        newest = seed.rows(conn, "SELECT id, is_trusted_device FROM user_sessions ORDER BY created_at DESC LIMIT 1")
    assert newest and newest[0]["is_trusted_device"] == 1
    assert newest[0]["id"].replace("-", "") == session_id.replace("-", "")


def test_session_cookie_survives_backend_app_restart(
    server: ServerUnderTest, alice: WeirClient, client_factory
) -> None:
    login = h.post_login(alice)
    assert login.status_code == 200, login.text
    cookie = alice.cookies.get(h.SESSION_COOKIE)
    assert cookie

    server.restart()

    after = h.client_with_cookie(client_factory, server, cookie)
    me = after.get(f"{API}/auth/me")
    assert me.status_code == 200, me.text
    assert me.json()["user"]["username"] == "alice"


def test_second_browser_login_does_not_revoke_first_browser_session(
    server: ServerUnderTest, alice: WeirClient, client_factory
) -> None:
    remote_client = client_factory(server)
    local_client = client_factory(server)
    assert h.post_login(remote_client).status_code == 200
    assert remote_client.get(f"{API}/auth/me").status_code == 200

    assert h.post_login(local_client).status_code == 200
    assert local_client.get(f"{API}/auth/me").status_code == 200
    assert remote_client.get(f"{API}/auth/me").status_code == 200


def test_authenticated_csrf_token_is_rejected_across_sessions(
    server: ServerUnderTest, alice: WeirClient, client_factory
) -> None:
    client_a = client_factory(server)
    client_b = client_factory(server)
    assert h.post_login(client_a).status_code == 200
    assert h.post_login(client_b).status_code == 200

    session_a_csrf = client_a.csrf()
    cross_session = client_b.post(
        f"{API}/auth/change-password",
        json={"csrf_token": session_a_csrf, "current_password": ADMIN_PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert cross_session.status_code == 400


def test_login_keeps_only_newest_five_active_sessions(server_factory, client_factory) -> None:
    sut = server_factory()
    h.ensure_admin_account(client_factory(sut))
    clients = [client_factory(sut) for _ in range(6)]
    for c in clients:
        login = h.post_login(c)
        assert login.status_code == 200, login.text

    assert clients[0].get(f"{API}/auth/me").status_code == 401
    for c in clients[1:]:
        assert c.get(f"{API}/auth/me").status_code == 200

    with seed.stopped(sut, restart=False) as conn:
        active = seed.scalar(conn, "SELECT COUNT(*) FROM user_sessions WHERE revoked_at IS NULL")
        revoked = seed.scalar(conn, "SELECT COUNT(*) FROM user_sessions WHERE revoked_at IS NOT NULL")
    assert active == 5
    assert revoked == 1


# Sessions that are already past their absolute expiry are deleted at server start, so a test that needs
# one alive at startup and expired at request time seeds it to expire shortly after the restart.
_EXPIRY_MARGIN = timedelta(seconds=15)


def test_session_limit_ignores_absolute_expired_sessions(server_factory, client_factory) -> None:
    sut = server_factory()
    h.ensure_admin_account(client_factory(sut))
    now = datetime.now(UTC)
    expires = now + _EXPIRY_MARGIN
    with seed.stopped(sut) as conn:
        uid = h.user_id(conn, ADMIN_USERNAME)
        expired_ids = [
            h.insert_session(
                conn,
                user=uid,
                created_at=now - timedelta(minutes=10 - i),
                absolute_expires_at=expires,
                last_seen_at=now,
            )[0]
            for i in range(5)
        ]
    h.wait_past(expires)

    live = client_factory(sut)
    assert h.post_login(live).status_code == 200
    assert live.get(f"{API}/auth/me").status_code == 200

    with seed.stopped(sut, restart=False) as conn:
        rows = seed.rows(conn, "SELECT id, revoked_at FROM user_sessions")
    by_id = {r["id"]: r for r in rows}
    assert set(expired_ids) <= set(by_id), "the expired sessions were cleaned up before the login ran"
    live_rows = [r for sid, r in by_id.items() if sid not in expired_ids]
    assert len(live_rows) == 1
    assert live_rows[0]["revoked_at"] is None
    assert all(by_id[sid]["revoked_at"] is None for sid in expired_ids)


def test_admin_ping_requires_admin(alice: WeirClient) -> None:
    h.post_login(alice)
    r = alice.get(f"{API}/auth/admin/ping")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_admin_ping_forbidden_for_viewer(server: ServerUnderTest, viewer_seeded: None, client_factory) -> None:
    c = client_factory(server)
    h.post_login(c, h.VIEWER_USERNAME, h.VIEWER_PASSWORD)
    r = c.get(f"{API}/auth/admin/ping")
    assert r.status_code == 403


def test_bootstrap_allowed_when_no_admin(server_factory, client_factory) -> None:
    sut = server_factory(env={"WEIR_BOOTSTRAP_RATE_MAX_ATTEMPTS": "100", "WEIR_BOOTSTRAP_RATE_WINDOW_SECONDS": "60"})
    c = client_factory(sut)
    r_s = c.get(f"{API}/auth/bootstrap/status")
    assert r_s.status_code == 200
    assert r_s.json()["bootstrap_allowed"] is True
    r_b = c.bootstrap("owner1", "first-owner-pass-min8")
    assert r_b.status_code == 200, r_b.text
    assert r_b.json()["username"] == "owner1"
    assert c.get(f"{API}/auth/bootstrap/status").json()["bootstrap_allowed"] is False
    r_login = h.post_login(c, "owner1", "first-owner-pass-min8")
    assert r_login.status_code == 200, r_login.text
    r_act = c.get(f"{API}/activity/recent")
    assert r_act.status_code == 200, r_act.text
    et = {x["event_type"] for x in r_act.json()["items"]}
    assert "auth.bootstrap_succeeded" in et
    assert "auth.login_succeeded" in et


@pytest.fixture(scope="module")
def no_admin_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[ServerUnderTest]:
    """No admin, one viewer called ``taken``. Bootstrap tests here must fail, so nothing changes."""

    sut = ServerUnderTest(home=tmp_path_factory.mktemp("weir_home"))
    sut.migrate()
    with seed.stopped(sut, restart=False) as conn:
        seed.insert_user(conn, username="taken", password="irrelevant-password-here", role="viewer")
    sut.start()
    try:
        yield sut
    finally:
        sut.stop()


def test_bootstrap_username_conflict_returns_409(no_admin_server: ServerUnderTest, client_factory) -> None:
    c = client_factory(no_admin_server)
    assert c.get(f"{API}/auth/bootstrap/status").json()["bootstrap_allowed"] is True
    r = c.bootstrap("taken", "valid-pass-bootstrap-8")
    assert r.status_code == 409


def test_bootstrap_rejects_short_password(no_admin_server: ServerUnderTest, client_factory) -> None:
    c = client_factory(no_admin_server)
    assert c.get(f"{API}/auth/bootstrap/status").json()["bootstrap_allowed"] is True
    r = c.bootstrap("owner1", "short")
    assert r.status_code == 422, r.text
    detail = r.json().get("detail") or []
    assert any(
        item.get("loc") == ["body", "password"] and "at least 8 characters" in item.get("msg", "")
        for item in detail
        if isinstance(item, dict)
    )


def test_bootstrap_rejects_common_password(no_admin_server: ServerUnderTest, client_factory) -> None:
    c = client_factory(no_admin_server)
    r = c.bootstrap("owner1", "password1234")
    assert r.status_code == 400, r.text
    assert "common" in r.json()["detail"].lower()


def test_bootstrap_blocked_after_admin_exists(alice: WeirClient) -> None:
    assert alice.get(f"{API}/auth/bootstrap/status").json()["bootstrap_allowed"] is False
    r_b = alice.bootstrap("intruder", "some-long-password-here")
    assert r_b.status_code == 403


def test_bootstrap_denied_persisted_throttled(server: ServerUnderTest, alice: WeirClient, client_factory) -> None:
    with seed.stopped(server) as conn:
        conn.execute("DELETE FROM activity_events WHERE event_type = 'auth.bootstrap_denied'")
        before = _count_events(conn, "auth.bootstrap_denied")
    c = client_factory(server)
    assert c.bootstrap("intruder", "some-long-password-here").status_code == 403
    assert c.bootstrap("intruder2", "other-long-password-here").status_code == 403
    with seed.stopped(server) as conn:
        after = _count_events(conn, "auth.bootstrap_denied")
    assert after - before == 1


def test_login_rate_limited(server_factory, client_factory) -> None:
    sut = server_factory(env={"WEIR_AUTH_LOGIN_RATE_MAX_ATTEMPTS": "3", "WEIR_AUTH_LOGIN_RATE_WINDOW_SECONDS": "120"})
    c = client_factory(sut)
    h.ensure_admin_account(c)
    for _ in range(3):
        r = h.post_login(c, password="wrong")
        assert r.status_code == 401, r.text
    r_limit = h.post_login(c, password="wrong")
    assert r_limit.status_code == 429
    assert "Retry-After" in r_limit.headers


def test_activity_recent_requires_authentication(alice: WeirClient) -> None:
    assert alice.get(f"{API}/activity/recent").status_code == 401


def test_activity_recent_includes_login_event(alice: WeirClient) -> None:
    r_login = h.post_login(alice)
    assert r_login.status_code == 200, r_login.text
    r_act = alice.get(f"{API}/activity/recent")
    assert r_act.status_code == 200, r_act.text
    items = r_act.json()["items"]
    assert any(x.get("event_type") == "auth.login_succeeded" and x.get("detail") == "alice" for x in items)


def test_activity_recent_includes_logout_event(alice: WeirClient) -> None:
    h.post_login(alice)
    r_out = alice.post(f"{API}/auth/logout", headers={"X-CSRF-Token": alice.csrf()})
    assert r_out.status_code == 204, r_out.text
    h.post_login(alice)
    r_act = alice.get(f"{API}/activity/recent")
    assert r_act.status_code == 200
    types = [x["event_type"] for x in r_act.json()["items"]]
    assert "auth.login_succeeded" in types
    assert "auth.logout" in types


def test_load_valid_session_throttles_last_seen_persistence(server_factory, client_factory) -> None:
    """Avoid persisting last_seen on every authenticated read (SQLite write pressure)."""

    sut = server_factory(env={"WEIR_SESSION_IDLE_MINUTES": "720"})
    h.ensure_admin_account(client_factory(sut))
    now = datetime.now(UTC)
    recent_seen = now
    old_seen = now - timedelta(minutes=10)
    with seed.stopped(sut) as conn:
        uid = h.user_id(conn, ADMIN_USERNAME)
        recent_id, recent_raw = h.insert_session(
            conn, user=uid, created_at=old_seen, absolute_expires_at=now + timedelta(days=1), last_seen_at=recent_seen
        )
        old_id, old_raw = h.insert_session(
            conn, user=uid, created_at=old_seen, absolute_expires_at=now + timedelta(days=1), last_seen_at=old_seen
        )

    # Well inside the 60 s touch gap for the recent session; well past it for the old one.
    assert h.client_with_cookie(client_factory, sut, recent_raw).get(f"{API}/auth/me").status_code == 200
    assert h.client_with_cookie(client_factory, sut, old_raw).get(f"{API}/auth/me").status_code == 200

    with seed.stopped(sut, restart=False) as conn:
        seen = {r["id"]: r["last_seen_at"] for r in seed.rows(conn, "SELECT id, last_seen_at FROM user_sessions")}
    assert h.parse_utc_text(seen[recent_id]) == recent_seen
    assert h.parse_utc_text(seen[old_id]) > old_seen + timedelta(minutes=5)


def test_expired_session_is_rejected_and_revoked(server_factory, client_factory) -> None:
    sut = server_factory(env={"WEIR_SESSION_IDLE_MINUTES": "720"})
    h.ensure_admin_account(client_factory(sut))
    now = datetime.now(UTC)
    expires = now + _EXPIRY_MARGIN
    with seed.stopped(sut) as conn:
        uid = h.user_id(conn, ADMIN_USERNAME)
        sid, raw = h.insert_session(conn, user=uid, created_at=now, absolute_expires_at=expires, last_seen_at=now)
    h.wait_past(expires)

    expired = h.client_with_cookie(client_factory, sut, raw)
    assert expired.get(f"{API}/auth/me").status_code == 401
    # A 401 rolls the request's writes back, so the revocation is persisted by a request that loads the
    # session and still succeeds: the CSRF fetch every page makes first (it falls back to an anonymous token).
    assert expired.get(f"{API}/auth/csrf").status_code == 200

    with seed.stopped(sut, restart=False) as conn:
        rows = seed.rows(conn, "SELECT revoked_at FROM user_sessions WHERE id = ?", (sid,))
    assert rows, "the session was cleaned up before the request ran"
    assert rows[0]["revoked_at"] is not None


def test_session_cleanup_deletes_revoked_and_expired_sessions(server_factory, client_factory) -> None:
    """The cleanup runs at server start (and hourly); a restart is the black-box trigger."""

    sut = server_factory(env={"WEIR_SESSION_IDLE_MINUTES": "720"})
    h.ensure_admin_account(client_factory(sut))
    now = datetime.now(UTC)
    with seed.stopped(sut) as conn:
        uid = h.user_id(conn, ADMIN_USERNAME)
        later = now + timedelta(days=1)
        h.insert_session(conn, user=uid, created_at=now, absolute_expires_at=later, last_seen_at=now, revoked_at=now)
        h.insert_session(
            conn, user=uid, created_at=now, absolute_expires_at=now - timedelta(seconds=1), last_seen_at=now
        )
        active_id, _ = h.insert_session(conn, user=uid, created_at=now, absolute_expires_at=later, last_seen_at=now)

    with seed.stopped(sut, restart=False) as conn:
        ids = [r["id"] for r in seed.rows(conn, "SELECT id FROM user_sessions")]
    assert ids == [active_id]


# --- security headers and the bundled web app ------------------------------------------------------


@pytest.fixture(scope="module")
def web_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[ServerUnderTest]:
    dist = h.write_web_dist(
        tmp_path_factory.mktemp("web") / "dist",
        "<!doctype html><html><body><div id='root'>Weir</div></body></html>",
    )
    (dist / "assets").mkdir()
    (dist / "assets" / "app.js").write_text("console.log('ok');", encoding="utf-8")
    env = {"WEIR_SECURITY_ENABLE_HSTS": "1", "WEIR_WEB_DIST": str(dist)}
    with h.own_server(tmp_path_factory, env) as sut:
        yield sut


def test_security_headers_on_health_and_api(web_server: ServerUnderTest, client_factory) -> None:
    c = client_factory(web_server)
    r_h = c.get("/health")
    assert r_h.headers.get("X-Content-Type-Options") == "nosniff"
    assert r_h.headers.get("X-Frame-Options") == "DENY"
    assert r_h.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert r_h.headers.get("Content-Security-Policy")
    assert r_h.headers.get("Cache-Control", "").startswith("no-store")
    assert r_h.headers.get("strict-transport-security")
    r_csrf = c.get(f"{API}/auth/csrf")
    assert r_csrf.headers.get("Content-Security-Policy")
    assert "frame-ancestors" in (r_csrf.headers.get("Content-Security-Policy") or "").lower()
    assert r_csrf.headers.get("Cache-Control", "").startswith("no-store")
    for path in (
        f"{API}/system/directories",
        f"{API}/suite/security-overview",
        f"{API}/suite/update-status",
        "/metrics",
    ):
        r = c.get(path)
        assert r.headers.get("Cache-Control", "").startswith("no-store"), path


def test_static_assets_do_not_get_api_no_store(web_server: ServerUnderTest, client_factory) -> None:
    response = client_factory(web_server).get("/assets/app.js")
    assert response.status_code == 200
    assert response.headers.get("Cache-Control") != "no-store, private"


def test_bundled_html_csp_does_not_allow_inline_styles(web_server: ServerUnderTest, client_factory) -> None:
    response = client_factory(web_server).get("/")
    assert response.status_code == 200
    csp = response.headers.get("Content-Security-Policy") or ""
    assert "style-src 'self'" in csp
    assert "fonts.googleapis.com" not in csp
    assert "fonts.gstatic.com" not in csp
    assert "'unsafe-inline'" not in csp


def test_spa_login_route_serves_index_html(web_server: ServerUnderTest, client_factory) -> None:
    response = client_factory(web_server).get("/login?session=expired", headers={"Accept": "text/html"})
    assert response.status_code == 200
    assert "text/html" in (response.headers.get("content-type") or "").lower()
    assert "Weir" in response.text


def test_missing_static_asset_still_returns_404(web_server: ServerUnderTest, client_factory) -> None:
    response = client_factory(web_server).get("/assets/missing.js", headers={"Accept": "*/*"})
    assert response.status_code == 404
