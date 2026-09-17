"""Contract port of apps/backend/tests/test_auth_cookie_secure_mode.py.

The sign-in cookie's ``Secure`` flag follows the request scheme (#452): a Secure cookie over plain
HTTP is silently discarded by browsers, locking the operator out.
"""

from __future__ import annotations

import pytest

from tests.contract.auth import _helpers as h
from tests.contract.support.client import API, WeirClient


@pytest.fixture
def alice(client: WeirClient) -> WeirClient:
    h.ensure_admin_account(client)
    return client


def test_plain_http_login_does_not_set_secure_cookie(alice: WeirClient) -> None:
    """The regression that locked operators out: a Secure cookie over HTTP is silently binned."""

    response = h.post_login(alice)
    assert response.status_code == 200, response.text

    set_cookie = h.set_cookie_header(response)
    assert set_cookie, "login must set a session cookie"
    assert "secure" not in set_cookie.lower()
    assert "httponly" in set_cookie.lower()

    me = alice.get(f"{API}/auth/me")
    assert me.status_code == 200, me.text


def test_forcing_always_still_sets_secure_over_plain_http(server_factory, client_factory) -> None:
    """An operator who explicitly forces it keeps the old behaviour, footgun included."""

    sut = server_factory(env={"WEIR_SESSION_COOKIE_SECURE": "always"})
    c = client_factory(sut)
    h.ensure_admin_account(c)
    response = h.post_login(c)
    assert response.status_code == 200, response.text
    assert "secure" in h.set_cookie_header(response).lower()


def test_forcing_never_does_not_set_secure_even_over_https(server_factory, client_factory) -> None:
    """``never`` wins over a request that a trusted proxy says arrived over HTTPS."""

    sut = server_factory(env={"WEIR_SESSION_COOKIE_SECURE": "never", "WEIR_TRUSTED_PROXY_IPS": "127.0.0.1/32"})
    c = client_factory(sut)
    h.ensure_admin_account(c)
    response = h.post_login(c, headers={"X-Forwarded-Proto": "https"})
    assert response.status_code == 200, response.text
    assert "secure" not in h.set_cookie_header(response).lower()


def test_logout_clears_the_cookie_it_set(alice: WeirClient) -> None:
    """Login and logout must agree on the flag, or the cookie is never actually cleared."""

    assert h.post_login(alice).status_code == 200

    logout = h.logout_with_body(alice)
    assert logout.status_code in (200, 204), logout.text

    cleared = h.set_cookie_header(logout)
    assert cleared, "logout must clear the session cookie"
    assert "secure" not in cleared.lower()

    assert alice.get(f"{API}/auth/me").status_code == 401
