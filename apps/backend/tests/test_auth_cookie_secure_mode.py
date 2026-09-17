"""The sign-in cookie's ``Secure`` flag follows the request scheme (#452).

Marking the cookie ``Secure`` on a plain-HTTP LAN install protects nothing — there is no TLS —
but the browser discards it, so the operator is bounced back to the login form with a correct
password and no error. These tests pin the three modes and both call sites.
"""

from __future__ import annotations

import dataclasses

import pytest
from starlette.testclient import TestClient

from tests.integration_helpers import auth_post
from tests.integration_helpers import csrf as fetch_csrf
from weir.platform.auth.sessions import resolve_cookie_secure


@pytest.mark.parametrize(
    ("scheme", "mode", "expected"),
    [
        ("http", "auto", False),
        ("https", "auto", True),
        ("http", "always", True),
        ("https", "always", True),
        ("http", "never", False),
        ("https", "never", False),
        ("HTTPS", "auto", True),
        ("", "auto", False),
    ],
)
def test_resolve_cookie_secure(scheme: str, mode: str, expected: bool) -> None:
    assert resolve_cookie_secure(scheme, mode) is expected


def _login(client: TestClient) -> object:
    csrf = fetch_csrf(client)
    return auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": csrf},
    )


def test_plain_http_login_does_not_set_secure_cookie(client_with_admin: TestClient) -> None:
    """The regression that locked operators out: a Secure cookie over HTTP is silently binned."""

    response = _login(client_with_admin)
    assert response.status_code == 200, response.text

    set_cookie = response.headers.get("set-cookie", "")
    assert set_cookie, "login must set a session cookie"
    assert "secure" not in set_cookie.lower()
    # The protections that do not depend on TLS must still be present.
    assert "httponly" in set_cookie.lower()

    # The session must actually survive, which is the thing the operator experiences.
    me = client_with_admin.get("/api/v1/auth/me")
    assert me.status_code == 200, me.text


def test_forcing_always_still_sets_secure_over_plain_http(
    client_with_admin: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An operator who explicitly forces it keeps the old behaviour, footgun included."""

    forced = dataclasses.replace(
        client_with_admin.app.state.settings,
        session_cookie_secure_mode="always",
    )
    monkeypatch.setattr(client_with_admin.app.state, "settings", forced, raising=False)

    response = _login(client_with_admin)
    assert response.status_code == 200, response.text
    assert "secure" in response.headers.get("set-cookie", "").lower()


def test_logout_clears_the_cookie_it_set(client_with_admin: TestClient) -> None:
    """Login and logout must agree on the flag, or the cookie is never actually cleared."""

    assert _login(client_with_admin).status_code == 200

    csrf = fetch_csrf(client_with_admin)
    logout = auth_post(client_with_admin, "/api/v1/auth/logout", json={"csrf_token": csrf})
    assert logout.status_code in (200, 204), logout.text

    cleared = logout.headers.get("set-cookie", "")
    assert cleared, "logout must clear the session cookie"
    assert "secure" not in cleared.lower()

    me = client_with_admin.get("/api/v1/auth/me")
    assert me.status_code == 401
