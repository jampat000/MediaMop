"""Authenticated read-only ``GET /api/v1/refiner/runtime-settings`` (Refiner-only worker snapshot)."""

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


def test_refiner_runtime_settings_requires_auth(client_with_admin: TestClient) -> None:
    r = client_with_admin.get("/api/v1/refiner/runtime-settings")
    assert r.status_code == 401


def test_refiner_runtime_settings_operator_shape(client_with_admin: TestClient) -> None:
    _login(client_with_admin)
    r = client_with_admin.get("/api/v1/refiner/runtime-settings")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["in_process_refiner_worker_count"] == 0
    assert body["in_process_workers_disabled"] is True
    assert body["in_process_workers_enabled"] is False
    assert "worker_mode_summary" in body
    assert "sqlite_throughput_note" in body
    assert "configuration_note" in body
    assert "visibility_note" in body
    assert "refiner_watched_folder_remux_scan_dispatch_schedule_enabled" in body
    assert "refiner_watched_folder_remux_scan_dispatch_schedule_interval_seconds" in body
    assert "refiner_watched_folder_remux_scan_dispatch_periodic_enqueue_remux_jobs" in body
    assert "refiner_watched_folder_remux_scan_dispatch_periodic_remux_dry_run" in body
    assert "refiner_watched_folder_min_file_age_seconds" in body
    assert "refiner_work_temp_stale_sweep_movie_schedule_enabled" in body
    assert "refiner_work_temp_stale_sweep_movie_schedule_interval_seconds" in body
    assert "refiner_work_temp_stale_sweep_tv_schedule_enabled" in body
    assert "refiner_work_temp_stale_sweep_tv_schedule_interval_seconds" in body
    assert "refiner_work_temp_stale_sweep_min_stale_age_seconds" in body
    assert "work_temp_stale_sweep_periodic_configuration_note" in body
    assert "watched_folder_scan_periodic_configuration_note" in body


def test_refiner_runtime_settings_viewer_forbidden(client_with_viewer: TestClient) -> None:
    tok = fetch_csrf(client_with_viewer)
    r = auth_post(
        client_with_viewer,
        "/api/v1/auth/login",
        json={"username": "bob", "password": "viewer-password-here", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text
    r2 = client_with_viewer.get("/api/v1/refiner/runtime-settings")
    assert r2.status_code == 403, r2.text
