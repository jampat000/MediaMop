import pytest
from starlette.testclient import TestClient

from mediamop.api.factory import create_app
from tests.integration_helpers import auth_post, csrf as fetch_csrf


def _login_admin(client: TestClient) -> None:
    tok = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


def test_metrics_requires_authentication(client_with_admin: TestClient) -> None:
    assert client_with_admin.get("/metrics").status_code == 401
    assert client_with_admin.get("/health").status_code == 200


def test_metrics_allows_operator_or_admin_session(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    r = client_with_admin.get("/metrics")
    assert r.status_code == 200, r.text
    assert "mediamop_http_requests_total" in r.text


def test_metrics_allows_bearer_token_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_METRICS_BEARER_TOKEN", "metrics-secret-token")
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/metrics", headers={"Authorization": "Bearer metrics-secret-token"})
    assert response.status_code == 200, response.text
    assert "mediamop_http_requests_total" in response.text


def test_metrics_rejects_invalid_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDIAMOP_METRICS_BEARER_TOKEN", "metrics-secret-token")
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/metrics", headers={"Authorization": "Bearer wrong-token"})
    assert response.status_code == 401
