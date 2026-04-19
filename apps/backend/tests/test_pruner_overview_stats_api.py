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


def test_pruner_overview_stats_requires_auth(client_with_admin: TestClient) -> None:
    r = client_with_admin.get("/api/v1/pruner/overview-stats")
    assert r.status_code == 401


def test_pruner_overview_stats_shape(client_with_admin: TestClient) -> None:
    _login(client_with_admin)
    r = client_with_admin.get("/api/v1/pruner/overview-stats")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["window_days"] == 30
    assert body["items_removed"] == 0
    assert body["items_skipped"] == 0
    assert body["apply_runs"] == 0
    assert body["preview_runs"] == 0
    assert body["failed_applies"] == 0
