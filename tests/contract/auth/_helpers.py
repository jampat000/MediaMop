"""Shared helpers for the auth contract tests."""

from __future__ import annotations

import contextlib
import hashlib
import secrets
import sqlite3
import time
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from tests.contract.support import seed
from tests.contract.support.client import ADMIN_PASSWORD, ADMIN_USERNAME, API, WeirClient
from tests.contract.support.launcher import ServerUnderTest

SESSION_COOKIE = "weir_session"
VIEWER_USERNAME = "bob"
VIEWER_PASSWORD = "viewer-password-here"


# --- servers --------------------------------------------------------------------------------------


@contextlib.contextmanager
def own_server(
    tmp_path_factory: pytest.TempPathFactory, env: dict[str, str] | None = None
) -> Iterator[ServerUnderTest]:
    """A started server with its own home, for module-scoped fixtures that need a special env."""

    sut = ServerUnderTest(home=tmp_path_factory.mktemp("weir_home"), env_overrides=dict(env or {}))
    try:
        sut.start()
    except RuntimeError as exc:
        pytest.fail(f"Weir contract could not start its server.\n{exc}", pytrace=False)
    try:
        yield sut
    finally:
        sut.stop()


def seeded_server(
    server_factory: Callable[..., ServerUnderTest],
    seed_fn: Callable[[sqlite3.Connection], None],
    env: dict[str, str] | None = None,
) -> ServerUnderTest:
    """A fresh server whose database was seeded by ``seed_fn`` before its first start."""

    sut = server_factory(env=env, start=False)
    sut.migrate()
    with seed.stopped(sut, restart=False) as conn:
        seed_fn(conn)
    sut.start()
    return sut


def write_web_dist(root: Path, index_html: str = "<!doctype html><div id='root'></div>") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "index.html").write_text(index_html, encoding="utf-8")
    return root


# --- accounts -------------------------------------------------------------------------------------


def ensure_admin_account(c: WeirClient) -> None:
    """Create the admin through bootstrap when the install has none, without signing in."""

    status = c.get(f"{API}/auth/bootstrap/status")
    assert status.status_code == 200, status.text
    if status.json().get("bootstrap_allowed"):
        r = c.bootstrap()
        assert r.status_code == 200, r.text


def ensure_viewer(server: ServerUnderTest) -> None:
    """Seed the viewer ``bob`` while the server is stopped (restarts it on a new port)."""

    with seed.stopped(server) as conn:
        if not seed.scalar(conn, "SELECT COUNT(*) FROM users WHERE username = ?", (VIEWER_USERNAME,)):
            seed.insert_user(conn, username=VIEWER_USERNAME, password=VIEWER_PASSWORD, role="viewer")


def login_body(c: WeirClient, username: str = ADMIN_USERNAME, password: str = ADMIN_PASSWORD, **extra: object) -> dict:
    return {"username": username, "password": password, "csrf_token": c.csrf(), **extra}


def post_login(
    c: WeirClient, username: str = ADMIN_USERNAME, password: str = ADMIN_PASSWORD, **kwargs
) -> httpx.Response:
    headers = kwargs.pop("headers", None)
    return c.post(f"{API}/auth/login", json=login_body(c, username, password, **kwargs), headers=headers)


def logout_with_body(c: WeirClient) -> httpx.Response:
    return c.post(f"{API}/auth/logout", json={"csrf_token": c.csrf()})


def set_cookie_header(response: httpx.Response) -> str:
    return "; ".join(response.headers.get_list("set-cookie"))


# --- sessions in SQLite ---------------------------------------------------------------------------


def user_id(conn: sqlite3.Connection, username: str) -> int:
    value = seed.scalar(conn, "SELECT id FROM users WHERE username = ?", (username,))
    assert value is not None, f"no user {username!r}"
    return int(value)


def insert_session(
    conn: sqlite3.Connection,
    *,
    user: int,
    created_at: datetime,
    absolute_expires_at: datetime,
    last_seen_at: datetime,
    revoked_at: datetime | None = None,
    trusted_device: bool = False,
) -> tuple[str, str]:
    """Insert a ``user_sessions`` row. Returns ``(session id hex, raw cookie token)``."""

    raw = secrets.token_urlsafe(32)
    sid = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO user_sessions (id, user_id, token_hash, created_at, absolute_expires_at, is_trusted_device, "
        "last_seen_at, revoked_at, client_label) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            sid,
            user,
            hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            seed.utc_text(created_at),
            seed.utc_text(absolute_expires_at),
            1 if trusted_device else 0,
            seed.utc_text(last_seen_at),
            None if revoked_at is None else seed.utc_text(revoked_at),
            "Browser session",
        ),
    )
    return sid, raw


def parse_utc_text(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def wait_past(moment: datetime) -> None:
    """Block until the wall clock is past ``moment`` (a deadline the test chose, not a guess)."""

    remaining = (moment - datetime.now(UTC)).total_seconds()
    if remaining > 0:
        time.sleep(remaining + 0.5)


def client_with_cookie(client_factory: Callable[..., WeirClient], server: ServerUnderTest, raw: str) -> WeirClient:
    c = client_factory(server)
    c.cookies.set(SESSION_COOKIE, raw)
    return c
