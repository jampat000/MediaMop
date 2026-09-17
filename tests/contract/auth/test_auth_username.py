"""Contract port of the retired Python backend's tests/test_auth_username.py (case-insensitive usernames, renaming, #455)."""

from __future__ import annotations

import pytest

from tests.contract.auth import _helpers as h
from tests.contract.support.client import ADMIN_PASSWORD, API, WeirClient


@pytest.fixture
def alice(client: WeirClient) -> WeirClient:
    h.ensure_admin_account(client)
    return client


@pytest.fixture
def own_alice(server_factory, client_factory) -> WeirClient:
    """``alice`` on a server of its own, for tests that rename the account."""

    c = client_factory(server_factory())
    h.ensure_admin_account(c)
    return c


def test_login_ignores_capitalisation(alice: WeirClient) -> None:
    """`alice` is seeded; `Alice` and `ALICE` are the same account, not a wrong password."""

    for spelling in ("alice", "Alice", "ALICE", "  AlIcE  "):
        response = h.post_login(alice, spelling)
        assert response.status_code == 200, f"{spelling!r}: {response.text}"
        h.logout_with_body(alice)


def test_a_wrong_password_is_still_rejected(alice: WeirClient) -> None:
    assert h.post_login(alice, "ALICE", "not-the-password").status_code == 401


def test_username_can_be_changed(own_alice: WeirClient) -> None:
    c = own_alice
    assert h.post_login(c, "alice").status_code == 200

    response = c.post_csrf(f"{API}/auth/change-username", {"current_password": ADMIN_PASSWORD, "new_username": "james"})
    assert response.status_code == 200, response.text
    assert response.json()["username"] == "james"

    # The session survives a rename: its authority is the token, not the name.
    assert c.get(f"{API}/auth/me").json()["user"]["username"] == "james"

    h.logout_with_body(c)
    assert h.post_login(c, "JAMES").status_code == 200
    assert h.post_login(c, "alice").status_code == 401


def test_changing_the_username_needs_the_current_password(alice: WeirClient) -> None:
    """The username is half of the credentials, so an unattended browser is not enough."""

    assert h.post_login(alice, "alice").status_code == 200

    response = alice.post_csrf(
        f"{API}/auth/change-username", {"current_password": "wrong-password", "new_username": "james"}
    )
    assert response.status_code == 400
    assert alice.get(f"{API}/auth/me").json()["user"]["username"] == "alice"


def test_fixing_your_own_capitalisation_is_allowed(own_alice: WeirClient) -> None:
    """`alice` -> `Alice` collides with nobody: it is the same row, tidying its own display."""

    c = own_alice
    assert h.post_login(c, "alice").status_code == 200

    response = c.post_csrf(f"{API}/auth/change-username", {"current_password": ADMIN_PASSWORD, "new_username": "Alice"})
    assert response.status_code == 200, response.text
    assert c.get(f"{API}/auth/me").json()["user"]["username"] == "Alice"

    h.logout_with_body(c)
    assert h.post_login(c, "alice").status_code == 200


def test_an_unchanged_username_is_refused(alice: WeirClient) -> None:
    assert h.post_login(alice, "alice").status_code == 200

    response = alice.post_csrf(
        f"{API}/auth/change-username", {"current_password": ADMIN_PASSWORD, "new_username": "alice"}
    )
    assert response.status_code == 400


def test_signed_out_callers_cannot_rename_anyone(alice: WeirClient) -> None:
    response = alice.post_csrf(
        f"{API}/auth/change-username", {"current_password": ADMIN_PASSWORD, "new_username": "james"}
    )
    assert response.status_code == 401
