"""Port of the retired Python backend's tests/test_metrics_auth.py."""

from __future__ import annotations

import pytest

from tests.contract.system import _helpers as h

METRICS_TOKEN = "metrics-secret-token"


@pytest.fixture(scope="module")
def server_env() -> dict[str, str]:
    # One server for the module: a configured bearer token does not change how sessions are treated.
    return {"WEIR_METRICS_BEARER_TOKEN": METRICS_TOKEN}


@pytest.fixture(scope="module", autouse=True)
def _users(server) -> None:
    h.seed_users(server)


def test_metrics_requires_authentication(client) -> None:
    assert client.get("/metrics").status_code == 401
    assert client.get("/health").status_code == 200


def test_metrics_allows_operator_or_admin_session(admin) -> None:
    r = admin.get("/metrics")
    assert r.status_code == 200, r.text
    assert "weir_http_requests_total" in r.text


def test_metrics_forbids_viewer_session(server, client_factory) -> None:
    viewer = h.signed_in_viewer(server, client_factory)
    assert viewer.get("/metrics").status_code == 403


def test_metrics_allows_bearer_token_when_configured(client) -> None:
    response = client.get("/metrics", headers={"Authorization": f"Bearer {METRICS_TOKEN}"})
    assert response.status_code == 200, response.text
    assert "weir_http_requests_total" in response.text


def test_metrics_rejects_invalid_bearer_token(client) -> None:
    response = client.get("/metrics", headers={"Authorization": "Bearer wrong-token"})
    assert response.status_code == 401
