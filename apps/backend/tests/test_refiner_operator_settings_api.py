"""GET/PUT /api/v1/refiner/operator-settings."""

from __future__ import annotations

from starlette.testclient import TestClient

from tests.integration_helpers import auth_post, csrf as fetch_csrf, trusted_browser_origin_headers


def _login_admin(client: TestClient) -> None:
    tok = fetch_csrf(client)
    r = auth_post(
        client,
        "/api/v1/auth/login",
        json={"username": "alice", "password": "test-password-strong", "csrf_token": tok},
    )
    assert r.status_code == 200, r.text


def test_refiner_operator_settings_get_shape(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    suite_r = client_with_admin.get("/api/v1/suite/settings")
    assert suite_r.status_code == 200, suite_r.text
    expected_schedule_tz = suite_r.json()["app_timezone"]
    r = client_with_admin.get("/api/v1/refiner/operator-settings")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["max_concurrent_files"] == 1
    assert body["min_file_age_seconds"] == 60
    assert body["movie_schedule_enabled"] is True
    assert "movie_schedule_interval_seconds" not in body
    assert body["movie_schedule_hours_limited"] is False
    assert body["movie_schedule_days"] == ""
    assert body["movie_schedule_start"] == "00:00"
    assert body["movie_schedule_end"] == "23:59"
    assert body["tv_schedule_enabled"] is True
    assert "tv_schedule_interval_seconds" not in body
    assert body["tv_schedule_hours_limited"] is False
    assert body["tv_schedule_days"] == ""
    assert body["tv_schedule_start"] == "00:00"
    assert body["tv_schedule_end"] == "23:59"
    assert body["schedule_timezone"] == expected_schedule_tz


def test_refiner_operator_settings_put_updates(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r = client_with_admin.put(
        "/api/v1/refiner/operator-settings",
        json={
            "csrf_token": tok,
            "max_concurrent_files": 4,
            "min_file_age_seconds": 90,
            "movie_schedule_enabled": True,
            "movie_schedule_hours_limited": True,
            "movie_schedule_days": "Mon,Tue",
            "movie_schedule_start": "09:00",
            "movie_schedule_end": "17:30",
            "tv_schedule_enabled": False,
            "tv_schedule_hours_limited": False,
            "tv_schedule_days": "",
            "tv_schedule_start": "00:00",
            "tv_schedule_end": "23:59",
        },
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["max_concurrent_files"] == 4
    assert body["min_file_age_seconds"] == 90
    assert body["movie_schedule_enabled"] is True
    assert body["movie_schedule_hours_limited"] is True
    assert body["movie_schedule_days"] == "Mon,Tue"
    assert body["movie_schedule_start"] == "09:00"
    assert body["movie_schedule_end"] == "17:30"
    assert body["tv_schedule_enabled"] is False
    assert body["tv_schedule_hours_limited"] is False


def test_refiner_operator_settings_put_tv_only_preserves_movie(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r0 = client_with_admin.put(
        "/api/v1/refiner/operator-settings",
        json={
            "csrf_token": tok,
            "movie_schedule_enabled": True,
            "movie_schedule_hours_limited": True,
            "movie_schedule_days": "Mon",
            "movie_schedule_start": "10:00",
            "movie_schedule_end": "11:00",
            "tv_schedule_enabled": True,
            "tv_schedule_hours_limited": False,
            "tv_schedule_days": "",
            "tv_schedule_start": "00:00",
            "tv_schedule_end": "23:59",
        },
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r0.status_code == 200, r0.text

    tok2 = fetch_csrf(client_with_admin)
    r1 = client_with_admin.put(
        "/api/v1/refiner/operator-settings",
        json={
            "csrf_token": tok2,
            "tv_schedule_enabled": False,
            "tv_schedule_hours_limited": True,
            "tv_schedule_days": "Wed",
            "tv_schedule_start": "08:00",
            "tv_schedule_end": "09:30",
        },
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r1.status_code == 200, r1.text
    body = r1.json()
    assert body["movie_schedule_hours_limited"] is True
    assert body["movie_schedule_days"] == "Mon"
    assert body["movie_schedule_start"] == "10:00"
    assert body["movie_schedule_end"] == "11:00"
    assert body["tv_schedule_enabled"] is False
    assert body["tv_schedule_hours_limited"] is True
    assert body["tv_schedule_days"] == "Wed"
    assert body["tv_schedule_start"] == "08:00"
    assert body["tv_schedule_end"] == "09:30"


def test_refiner_operator_settings_put_process_only_preserves_schedules(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r0 = client_with_admin.put(
        "/api/v1/refiner/operator-settings",
        json={
            "csrf_token": tok,
            "movie_schedule_enabled": True,
            "movie_schedule_hours_limited": False,
            "movie_schedule_days": "",
            "movie_schedule_start": "00:00",
            "movie_schedule_end": "23:59",
            "tv_schedule_enabled": True,
            "tv_schedule_hours_limited": False,
            "tv_schedule_days": "",
            "tv_schedule_start": "00:00",
            "tv_schedule_end": "23:59",
        },
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r0.status_code == 200, r0.text

    tok2 = fetch_csrf(client_with_admin)
    r1 = client_with_admin.put(
        "/api/v1/refiner/operator-settings",
        json={
            "csrf_token": tok2,
            "max_concurrent_files": 3,
            "min_file_age_seconds": 120,
        },
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r1.status_code == 200, r1.text
    body = r1.json()
    assert body["max_concurrent_files"] == 3
    assert body["min_file_age_seconds"] == 120
    assert body["movie_schedule_hours_limited"] is False
    assert body["tv_schedule_hours_limited"] is False


def test_refiner_operator_settings_put_rejects_partial_movie_schedule_group(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r = client_with_admin.put(
        "/api/v1/refiner/operator-settings",
        json={
            "csrf_token": tok,
            "movie_schedule_enabled": True,
            "movie_schedule_hours_limited": False,
            "movie_schedule_days": "",
            "movie_schedule_start": "00:00",
            # movie_schedule_end omitted on purpose
        },
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 422, r.text


def test_refiner_operator_settings_put_rejects_csrf_only(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r = client_with_admin.put(
        "/api/v1/refiner/operator-settings",
        json={"csrf_token": tok},
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 422, r.text


def test_refiner_operator_settings_put_invalid_days(client_with_admin: TestClient) -> None:
    _login_admin(client_with_admin)
    tok = fetch_csrf(client_with_admin)
    r = client_with_admin.put(
        "/api/v1/refiner/operator-settings",
        json={
            "csrf_token": tok,
            "max_concurrent_files": 1,
            "min_file_age_seconds": 60,
            "movie_schedule_enabled": True,
            "movie_schedule_hours_limited": False,
            "movie_schedule_days": "Caturday",
            "movie_schedule_start": "00:00",
            "movie_schedule_end": "23:59",
            "tv_schedule_enabled": True,
            "tv_schedule_hours_limited": False,
            "tv_schedule_days": "",
            "tv_schedule_start": "00:00",
            "tv_schedule_end": "23:59",
        },
        headers={**trusted_browser_origin_headers(), "Content-Type": "application/json"},
    )
    assert r.status_code == 400, r.text
