"""Port of the retired Python backend's tests/test_processing_runtime_settings_api.py."""

from __future__ import annotations

from tests.contract.libraries import _helpers as h
from tests.contract.support.client import API

PATH = f"{API}/processing/runtime-settings"


def test_processing_runtime_settings_requires_auth(client) -> None:
    r = client.get(PATH)
    assert r.status_code == 401


def test_processing_runtime_settings_operator_shape(admin) -> None:
    r = admin.get(PATH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["in_process_processing_worker_count"] == 0
    assert body["in_process_workers_disabled"] is True
    assert body["in_process_workers_enabled"] is False
    for key in (
        "worker_mode_summary",
        "sqlite_throughput_note",
        "configuration_note",
        "visibility_note",
        "processing_watched_folder_remux_scan_dispatch_periodic_enqueue_remux_jobs",
        "processing_probe_size_mb",
        "processing_analyze_duration_seconds",
        "processing_watched_folder_min_file_age_seconds",
        "processing_movie_output_cleanup_min_age_seconds",
        "movie_output_cleanup_configuration_note",
        "processing_tv_output_cleanup_min_age_seconds",
        "tv_output_cleanup_configuration_note",
        "processing_work_temp_stale_sweep_movie_schedule_enabled",
        "processing_work_temp_stale_sweep_movie_schedule_interval_seconds",
        "processing_work_temp_stale_sweep_tv_schedule_enabled",
        "processing_work_temp_stale_sweep_tv_schedule_interval_seconds",
        "processing_work_temp_stale_sweep_min_stale_age_seconds",
        "processing_movie_failure_cleanup_schedule_enabled",
        "processing_movie_failure_cleanup_schedule_interval_seconds",
        "processing_tv_failure_cleanup_schedule_enabled",
        "processing_tv_failure_cleanup_schedule_interval_seconds",
        "processing_movie_failure_cleanup_grace_period_seconds",
        "processing_tv_failure_cleanup_grace_period_seconds",
        "failure_cleanup_configuration_note",
        "work_temp_stale_sweep_periodic_configuration_note",
        "watched_folder_scan_periodic_configuration_note",
    ):
        assert key in body, key
    # Removed in #329: both reported themselves as live startup configuration while the
    # scheduler read the per-scope database toggles instead.
    assert "processing_watched_folder_remux_scan_dispatch_schedule_enabled" not in body
    assert "processing_watched_folder_remux_scan_dispatch_schedule_interval_seconds" not in body


def test_processing_runtime_settings_viewer_forbidden(server, client_factory) -> None:
    h.ensure_viewer(server)
    viewer = h.signed_in_viewer(server, client_factory)
    r2 = viewer.get(PATH)
    assert r2.status_code == 403, r2.text
