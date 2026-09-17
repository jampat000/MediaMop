"""Shared helpers for the system contract tests."""

from __future__ import annotations

from collections.abc import Callable

from tests.contract.support import seed
from tests.contract.support.client import ADMIN_PASSWORD, ADMIN_USERNAME, WeirClient
from tests.contract.support.launcher import ServerUnderTest

VIEWER_USERNAME = "bob"
VIEWER_PASSWORD = "viewer-password-here"

# Every outbound HTTP(S) client the server builds from the environment goes through this proxy,
# which refuses connections: an update check can never reach the internet from a contract run.
NO_INTERNET_ENV = {
    "HTTPS_PROXY": "http://127.0.0.1:9",
    "HTTP_PROXY": "http://127.0.0.1:9",
    "ALL_PROXY": "http://127.0.0.1:9",
    "NO_PROXY": "",
}


def seed_users(server: ServerUnderTest) -> None:
    """Seed the admin ``alice`` and the viewer ``bob`` while the server is stopped (restarts it on a new port).

    The admin is seeded too because bootstrap is refused once any user exists.
    """

    with seed.stopped(server) as conn:
        if not seed.scalar(conn, "SELECT COUNT(*) FROM users WHERE username = ?", (ADMIN_USERNAME,)):
            seed.insert_user(conn, username=ADMIN_USERNAME, password=ADMIN_PASSWORD, role="admin")
        if not seed.scalar(conn, "SELECT COUNT(*) FROM users WHERE username = ?", (VIEWER_USERNAME,)):
            seed.insert_user(conn, username=VIEWER_USERNAME, password=VIEWER_PASSWORD, role="viewer")


def signed_in_admin(server: ServerUnderTest, client_factory: Callable[..., WeirClient]) -> WeirClient:
    c = client_factory(server)
    c.ensure_admin()
    return c


def signed_in_viewer(server: ServerUnderTest, client_factory: Callable[..., WeirClient]) -> WeirClient:
    c = client_factory(server)
    c.login(VIEWER_USERNAME, VIEWER_PASSWORD)
    return c
