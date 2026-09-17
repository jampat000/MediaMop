"""HTTP-observable rate limiting (apps/backend/tests/test_rate_limit.py tests the limiter class directly).

Login and bootstrap each have a per-address sliding window configured by
``WEIR_AUTH_LOGIN_RATE_*`` and ``WEIR_BOOTSTRAP_RATE_*``; exceeding it answers 429 with ``Retry-After``.
"""

from __future__ import annotations

import pytest

from tests.contract.auth import _helpers as h
from tests.contract.support.client import WeirClient
from tests.contract.support.polling import wait_until

WINDOW_SECONDS = 2


@pytest.fixture(scope="module")
def server_env() -> dict[str, str]:
    return {
        "WEIR_AUTH_LOGIN_RATE_MAX_ATTEMPTS": "2",
        "WEIR_AUTH_LOGIN_RATE_WINDOW_SECONDS": str(WINDOW_SECONDS),
        "WEIR_BOOTSTRAP_RATE_MAX_ATTEMPTS": "2",
        "WEIR_BOOTSTRAP_RATE_WINDOW_SECONDS": "3600",
    }


def test_login_rate_limit_window_slides(client: WeirClient) -> None:
    assert h.post_login(client, password="wrong").status_code == 401
    assert h.post_login(client, password="wrong").status_code == 401
    limited = h.post_login(client, password="wrong")
    assert limited.status_code == 429
    assert limited.headers.get("Retry-After") == str(WINDOW_SECONDS)

    wait_until(
        lambda: h.post_login(client, password="wrong").status_code == 401,
        timeout_s=WINDOW_SECONDS * 5,
        interval_s=0.5,
        what="the login window to slide past the earlier attempts",
    )


def test_bootstrap_rate_limited(client: WeirClient) -> None:
    for _ in range(2):
        assert client.bootstrap("owner1", "password1234").status_code == 400
    limited = client.bootstrap("owner1", "password1234")
    assert limited.status_code == 429
    assert limited.headers.get("Retry-After") == "3600"
