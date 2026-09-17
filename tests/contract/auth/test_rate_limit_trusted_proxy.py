"""HTTP-observable parts of apps/backend/tests/test_rate_limit_trusted_proxy.py.

With ``WEIR_TRUSTED_PROXY_IPS`` covering the peer, the login rate limit is keyed on the rightmost
untrusted ``X-Forwarded-For`` address, so clients behind one proxy do not share a bucket.
"""

from __future__ import annotations

import pytest

from tests.contract.auth import _helpers as h
from tests.contract.support.client import WeirClient


@pytest.fixture(scope="module")
def server_env() -> dict[str, str]:
    return {
        "WEIR_TRUSTED_PROXY_IPS": "127.0.0.1/32",
        "WEIR_AUTH_LOGIN_RATE_MAX_ATTEMPTS": "2",
        "WEIR_AUTH_LOGIN_RATE_WINDOW_SECONDS": "3600",
    }


def _attempt(c: WeirClient, forwarded_for: str) -> int:
    return h.post_login(c, password="wrong", headers={"X-Forwarded-For": forwarded_for}).status_code


def test_rate_limit_uses_forwarded_for_from_trusted_proxy(client: WeirClient) -> None:
    assert _attempt(client, "203.0.113.10") == 401
    assert _attempt(client, "203.0.113.10") == 401
    assert _attempt(client, "203.0.113.10") == 429
    # Another client behind the same proxy has its own window.
    assert _attempt(client, "203.0.113.11") == 401


def test_rate_limit_uses_rightmost_untrusted_forwarded_for_from_trusted_proxy(client: WeirClient) -> None:
    assert _attempt(client, "203.0.113.7") == 401
    assert _attempt(client, "203.0.113.7") == 401
    # The client-supplied left part of the chain does not escape the bucket of the address the proxy saw.
    assert _attempt(client, "198.51.100.20, 203.0.113.7") == 429
    assert _attempt(client, "198.51.100.20, 203.0.113.7, 127.0.0.1") == 429
    # A different rightmost address is a different client.
    assert _attempt(client, "203.0.113.7, 198.51.100.20") == 401
