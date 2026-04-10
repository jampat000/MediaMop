"""Authenticated read-only ``GET /api/v1/fetcher/failed-imports/settings`` (Fetcher failed-import workflow)."""

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


def test_fetcher_failed_imports_settings_requires_auth(client_with_admin: TestClient) -> None:
    r = client_with_admin.get("/api/v1/fetcher/failed-imports/settings")
    assert r.status_code == 401


def test_fetcher_failed_imports_settings_authenticated_shape(client_with_admin: TestClient) -> None:
    _login(client_with_admin)
    r = client_with_admin.get("/api/v1/fetcher/failed-imports/settings")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["refiner_worker_count"] == 0
    assert body["in_process_workers_disabled"] is True
    assert body["in_process_workers_enabled"] is False
    assert "refiner_radarr_cleanup_drive_schedule_enabled" in body
    assert "refiner_radarr_cleanup_drive_schedule_interval_seconds" in body
    assert "refiner_sonarr_cleanup_drive_schedule_enabled" in body
    assert "refiner_sonarr_cleanup_drive_schedule_interval_seconds" in body
    assert "worker_mode_summary" in body
    assert "visibility_note" in body
