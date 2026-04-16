from __future__ import annotations

from starlette.testclient import TestClient

from tests.integration_helpers import auth_post, csrf as fetch_csrf


def _login(client: TestClient) -> None:
    tok = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


def test_refiner_overview_stats_requires_auth(client_with_admin: TestClient) -> None:
    r = client_with_admin.get("/api/v1/refiner/overview-stats")
    assert r.status_code == 401


def test_refiner_overview_stats_shape(client_with_admin: TestClient) -> None:
    _login(client_with_admin)
    r = client_with_admin.get("/api/v1/refiner/overview-stats")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["window_days"] == 30
    assert "files_processed" in body
    assert "files_failed" in body
    assert isinstance(body["files_failed"], int)
    assert "success_rate_percent" in body
    assert "space_saved_available" not in body
