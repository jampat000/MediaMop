"""Contract port of the HTTP-observable parts of apps/backend/tests/test_csrf_unit.py.

The original's only HTTP test is the 503 without a session secret. Its Origin/Referer and loopback
pairing unit tests are expressed here through ``POST /auth/login`` on configured servers.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests.contract.auth import _helpers as h
from tests.contract.support.client import API, WeirClient
from tests.contract.support.launcher import ServerUnderTest

TRUSTED = "http://127.0.0.1:9000"
CORS_ONLY = "http://127.0.0.1:8782"
XRW = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture(scope="module")
def server_env() -> dict[str, str]:
    # WEIR_TRUSTED_BROWSER_ORIGINS overrides WEIR_CORS_ORIGINS for the Origin check.
    return {"WEIR_TRUSTED_BROWSER_ORIGINS": TRUSTED, "WEIR_CORS_ORIGINS": CORS_ONLY}


@pytest.fixture(scope="module")
def _admin(server: ServerUnderTest) -> Iterator[None]:
    with WeirClient(server.base_url, headers={"Origin": TRUSTED, **XRW}) as c:
        h.ensure_admin_account(c)
    yield


def _login(c: WeirClient, headers: dict[str, str]) -> int:
    return h.post_login(c, headers=headers).status_code


def test_auth_csrf_endpoint_503_without_session_secret(server_factory, client_factory) -> None:
    sut = server_factory(env={"WEIR_SESSION_SECRET": ""})
    r = client_factory(sut).get(f"{API}/auth/csrf")
    assert r.status_code == 503


def test_origin_skipped_when_no_trusted_list(server_factory, client_factory) -> None:
    sut = server_factory()
    c = client_factory(sut)
    h.ensure_admin_account(c)
    assert _login(c, {}) == 200
    assert _login(c, {"Origin": "http://evil.test", **XRW}) == 200


def test_origin_enforced_when_configured(_admin: None, client: WeirClient) -> None:
    assert _login(client, {"Origin": TRUSTED, **XRW}) == 200
    assert _login(client, {"Origin": "http://evil.test", **XRW}) == 403


def test_referer_checked_when_origin_absent(_admin: None, client: WeirClient) -> None:
    assert _login(client, {"Referer": f"{TRUSTED}/login"}) == 200
    assert _login(client, {"Referer": "http://evil.test/login"}) == 403
    assert _login(client, {}) == 403


def test_origin_uses_trusted_browser_origins_override(_admin: None, client: WeirClient) -> None:
    assert _login(client, {"Origin": CORS_ONLY, **XRW}) == 403


def test_expand_loopback_browser_origins_pairs_localhost(_admin: None, client: WeirClient) -> None:
    """In development (the default WEIR_ENV) 127.0.0.1 and localhost at the same port are paired."""

    assert _login(client, {"Origin": "http://localhost:9000", **XRW}) == 200
    assert _login(client, {"Origin": "http://localhost:9001", **XRW}) == 403
