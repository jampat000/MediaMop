"""Contract port of apps/backend/tests/test_cors_policy.py."""

from __future__ import annotations

import pytest

from tests.contract.support.client import API, WeirClient

ORIGIN = "http://localhost:5173"


@pytest.fixture(scope="module")
def server_env() -> dict[str, str]:
    return {"WEIR_CORS_ORIGINS": ORIGIN}


def test_cors_preflight_allows_weir_browser_methods_and_headers(client: WeirClient) -> None:
    response = client.options(
        f"{API}/auth/csrf",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, X-CSRF-Token",
        },
    )

    assert response.status_code == 200
    methods = response.headers["access-control-allow-methods"]
    headers = response.headers["access-control-allow-headers"]
    assert "GET" in methods
    assert "POST" in methods
    assert "OPTIONS" in methods
    assert "content-type" in headers.lower()
    assert "x-csrf-token" in headers.lower()


def test_cors_preflight_rejects_unneeded_methods(client: WeirClient) -> None:
    trace = client.options(
        f"{API}/auth/csrf",
        headers={"Origin": ORIGIN, "Access-Control-Request-Method": "TRACE"},
    )
    connect = client.options(
        f"{API}/auth/csrf",
        headers={"Origin": ORIGIN, "Access-Control-Request-Method": "CONNECT"},
    )

    assert trace.status_code == 400
    assert connect.status_code == 400
    assert "TRACE" not in trace.headers.get("access-control-allow-methods", "")
    assert "CONNECT" not in connect.headers.get("access-control-allow-methods", "")


def test_cors_preflight_rejects_unneeded_headers(client: WeirClient) -> None:
    response = client.options(
        f"{API}/auth/csrf",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-Injected-Header",
        },
    )

    assert response.status_code == 400
