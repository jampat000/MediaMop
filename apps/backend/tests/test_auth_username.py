"""Case-insensitive usernames, and changing the operator's name (#455)."""

from __future__ import annotations

from starlette.testclient import TestClient

from tests.integration_helpers import auth_post
from tests.integration_helpers import csrf as fetch_csrf

_PASSWORD = "test-password-strong"


def _login(client: TestClient, username: str, password: str = _PASSWORD):
    csrf = fetch_csrf(client)
    return auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": username, "password": password, "csrf_token": csrf},
    )


def test_login_ignores_capitalisation(client_with_admin: TestClient) -> None:
    """`alice` is seeded; `Alice` and `ALICE` are the same account, not a wrong password."""

    for spelling in ("alice", "Alice", "ALICE", "  AlIcE  "):
        response = _login(client_with_admin, spelling)
        assert response.status_code == 200, f"{spelling!r}: {response.text}"

        csrf = fetch_csrf(client_with_admin)
        auth_post(client_with_admin, "/api/v1/auth/logout", json={"csrf_token": csrf})


def test_a_wrong_password_is_still_rejected(client_with_admin: TestClient) -> None:
    assert _login(client_with_admin, "ALICE", "not-the-password").status_code == 401


def test_username_can_be_changed(client_with_admin: TestClient) -> None:
    assert _login(client_with_admin, "alice").status_code == 200

    csrf = fetch_csrf(client_with_admin)
    response = auth_post(
        client_with_admin,
        "/api/v1/auth/change-username",
        json={"current_password": _PASSWORD, "new_username": "james", "csrf_token": csrf},
    )
    assert response.status_code == 200, response.text
    assert response.json()["username"] == "james"

    # The session survives a rename — its authority is the token, not the name.
    assert client_with_admin.get("/api/v1/auth/me").json()["user"]["username"] == "james"

    csrf = fetch_csrf(client_with_admin)
    auth_post(client_with_admin, "/api/v1/auth/logout", json={"csrf_token": csrf})
    assert _login(client_with_admin, "JAMES").status_code == 200
    assert _login(client_with_admin, "alice").status_code == 401


def test_changing_the_username_needs_the_current_password(client_with_admin: TestClient) -> None:
    """The username is half of the credentials, so an unattended browser is not enough."""

    assert _login(client_with_admin, "alice").status_code == 200

    csrf = fetch_csrf(client_with_admin)
    response = auth_post(
        client_with_admin,
        "/api/v1/auth/change-username",
        json={"current_password": "wrong-password", "new_username": "james", "csrf_token": csrf},
    )
    assert response.status_code == 400
    assert client_with_admin.get("/api/v1/auth/me").json()["user"]["username"] == "alice"


def test_fixing_your_own_capitalisation_is_allowed(client_with_admin: TestClient) -> None:
    """`alice` -> `Alice` collides with nobody: it is the same row, tidying its own display."""

    assert _login(client_with_admin, "alice").status_code == 200

    csrf = fetch_csrf(client_with_admin)
    response = auth_post(
        client_with_admin,
        "/api/v1/auth/change-username",
        json={"current_password": _PASSWORD, "new_username": "Alice", "csrf_token": csrf},
    )
    assert response.status_code == 200, response.text
    assert client_with_admin.get("/api/v1/auth/me").json()["user"]["username"] == "Alice"

    # Sign-in still ignores case, so nothing about how they log in has changed.
    csrf = fetch_csrf(client_with_admin)
    auth_post(client_with_admin, "/api/v1/auth/logout", json={"csrf_token": csrf})
    assert _login(client_with_admin, "alice").status_code == 200


def test_an_unchanged_username_is_refused(client_with_admin: TestClient) -> None:
    assert _login(client_with_admin, "alice").status_code == 200

    csrf = fetch_csrf(client_with_admin)
    response = auth_post(
        client_with_admin,
        "/api/v1/auth/change-username",
        json={"current_password": _PASSWORD, "new_username": "alice", "csrf_token": csrf},
    )
    assert response.status_code == 400


def test_signed_out_callers_cannot_rename_anyone(client_with_admin: TestClient) -> None:
    csrf = fetch_csrf(client_with_admin)
    response = auth_post(
        client_with_admin,
        "/api/v1/auth/change-username",
        json={"current_password": _PASSWORD, "new_username": "james", "csrf_token": csrf},
    )
    assert response.status_code == 401
