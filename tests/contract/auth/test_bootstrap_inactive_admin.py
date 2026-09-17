"""HTTP-observable parts of apps/backend/tests/test_bootstrap_inactive_admin.py.

A deactivated sole admin must not brick the install (#456): sign-in rejects it, so bootstrap reopens.
"""

from __future__ import annotations

from tests.contract.auth import _helpers as h
from tests.contract.support import seed
from tests.contract.support.client import ADMIN_PASSWORD, ADMIN_USERNAME, API


def _seed_admin(active: bool):
    def seed_fn(conn) -> None:
        seed.insert_user(conn, username=ADMIN_USERNAME, password=ADMIN_PASSWORD, role="admin", is_active=active)

    return seed_fn


def test_active_admin_still_closes_bootstrap(server_factory, client_factory) -> None:
    sut = h.seeded_server(server_factory, _seed_admin(active=True))
    c = client_factory(sut)
    assert c.get(f"{API}/auth/bootstrap/status").json()["bootstrap_allowed"] is False
    assert h.post_login(c).status_code == 200


def test_inactive_sole_admin_reopens_bootstrap(server_factory, client_factory) -> None:
    sut = h.seeded_server(server_factory, _seed_admin(active=False))
    c = client_factory(sut)
    assert h.post_login(c).status_code == 401
    assert c.get(f"{API}/auth/bootstrap/status").json()["bootstrap_allowed"] is True


def test_recovering_from_an_inactive_admin_leaves_exactly_one(server_factory, client_factory) -> None:
    """The install must come back with one usable admin, never two rows."""

    sut = h.seeded_server(server_factory, _seed_admin(active=False))
    c = client_factory(sut)
    r = c.bootstrap("alice-again", "recovered-password-strong")
    assert r.status_code == 200, r.text
    assert c.get(f"{API}/auth/bootstrap/status").json()["bootstrap_allowed"] is False
    assert h.post_login(c, "alice-again", "recovered-password-strong").status_code == 200

    with seed.stopped(sut, restart=False) as conn:
        admins = seed.rows(conn, "SELECT username, is_active FROM users WHERE role = 'admin'")
    assert admins == [{"username": "alice-again", "is_active": 1}]
