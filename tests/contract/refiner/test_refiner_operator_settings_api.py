"""Port of apps/backend/tests/test_refiner_operator_settings_api.py."""

from __future__ import annotations

from tests.contract.refiner import _helpers as h
from tests.contract.support.client import API

PATH = f"{API}/refiner/operator-settings"

ALL_OPEN_SCHEDULES = {
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
}


def test_refiner_operator_settings_get_shape(server_factory, client_factory) -> None:
    # A fresh install, so the defaults are not disturbed by the PUT tests in this module.
    admin = h.signed_in_admin(server_factory(), client_factory)
    suite_r = admin.get(f"{API}/suite/settings")
    assert suite_r.status_code == 200, suite_r.text
    expected_schedule_tz = suite_r.json()["app_timezone"]
    r = admin.get(PATH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["max_concurrent_files"] == 1
    assert body["min_file_age_seconds"] == 60
    assert body["refiner_min_input_file_size_mb"] == 50
    assert body["minimum_free_disk_space_mb"] == 5120
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


def test_refiner_operator_settings_put_updates(admin) -> None:
    r = admin.put_csrf(
        PATH,
        {
            "max_concurrent_files": 4,
            "min_file_age_seconds": 90,
            "refiner_min_input_file_size_mb": 75,
            "minimum_free_disk_space_mb": 6144,
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
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["max_concurrent_files"] == 4
    assert body["min_file_age_seconds"] == 90
    assert body["refiner_min_input_file_size_mb"] == 75
    assert body["minimum_free_disk_space_mb"] == 6144
    assert body["movie_schedule_enabled"] is True
    assert body["movie_schedule_hours_limited"] is True
    assert body["movie_schedule_days"] == "Mon,Tue"
    assert body["movie_schedule_start"] == "09:00"
    assert body["movie_schedule_end"] == "17:30"
    assert body["tv_schedule_enabled"] is False
    assert body["tv_schedule_hours_limited"] is False
    # And the saved values are what a later read returns.
    again = admin.get(PATH).json()
    assert again["max_concurrent_files"] == 4
    assert again["movie_schedule_days"] == "Mon,Tue"


def test_refiner_operator_settings_put_tv_only_preserves_movie(admin) -> None:
    r0 = admin.put_csrf(
        PATH,
        {
            **ALL_OPEN_SCHEDULES,
            "movie_schedule_hours_limited": True,
            "movie_schedule_days": "Mon",
            "movie_schedule_start": "10:00",
            "movie_schedule_end": "11:00",
        },
    )
    assert r0.status_code == 200, r0.text

    r1 = admin.put_csrf(
        PATH,
        {
            "tv_schedule_enabled": False,
            "tv_schedule_hours_limited": True,
            "tv_schedule_days": "Wed",
            "tv_schedule_start": "08:00",
            "tv_schedule_end": "09:30",
        },
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


def test_refiner_operator_settings_put_process_only_preserves_schedules(admin) -> None:
    r0 = admin.put_csrf(PATH, ALL_OPEN_SCHEDULES)
    assert r0.status_code == 200, r0.text

    r1 = admin.put_csrf(
        PATH,
        {
            "max_concurrent_files": 3,
            "min_file_age_seconds": 120,
            "refiner_min_input_file_size_mb": 80,
            "minimum_free_disk_space_mb": 8192,
        },
    )
    assert r1.status_code == 200, r1.text
    body = r1.json()
    assert body["max_concurrent_files"] == 3
    assert body["min_file_age_seconds"] == 120
    assert body["refiner_min_input_file_size_mb"] == 80
    assert body["minimum_free_disk_space_mb"] == 8192
    assert body["movie_schedule_hours_limited"] is False
    assert body["tv_schedule_hours_limited"] is False


def test_refiner_operator_settings_put_rejects_partial_movie_schedule_group(admin) -> None:
    r = admin.put_csrf(
        PATH,
        {
            "movie_schedule_enabled": True,
            "movie_schedule_hours_limited": False,
            "movie_schedule_days": "",
            "movie_schedule_start": "00:00",
            # movie_schedule_end omitted on purpose
        },
    )
    assert r.status_code == 422, r.text


def test_refiner_operator_settings_put_rejects_csrf_only(admin) -> None:
    r = admin.put_csrf(PATH, {})
    assert r.status_code == 422, r.text


def test_refiner_operator_settings_put_invalid_days(admin) -> None:
    r = admin.put_csrf(
        PATH,
        {
            **ALL_OPEN_SCHEDULES,
            "max_concurrent_files": 1,
            "min_file_age_seconds": 60,
            "movie_schedule_days": "Caturday",
        },
    )
    assert r.status_code == 400, r.text
