"""Guardrails for ADR-0009: per-lane timing fields exist on ``MediaMopSettings`` (Fetcher + Refiner)."""

from __future__ import annotations

from dataclasses import fields

from mediamop.core.config import MediaMopSettings


def _field_names() -> set[str]:
    return {f.name for f in fields(MediaMopSettings)}


def test_fetcher_arr_search_has_four_distinct_lane_timing_surfaces() -> None:
    """Each of the four search lanes must expose its own max/retry/schedule settings (no single shared sonarr/radarr retry field)."""

    names = _field_names()
    required = {
        "fetcher_sonarr_missing_search_max_items_per_run",
        "fetcher_sonarr_missing_search_retry_delay_minutes",
        "fetcher_sonarr_missing_search_schedule_enabled",
        "fetcher_sonarr_upgrade_search_max_items_per_run",
        "fetcher_sonarr_upgrade_search_retry_delay_minutes",
        "fetcher_sonarr_upgrade_search_schedule_enabled",
        "fetcher_radarr_missing_search_max_items_per_run",
        "fetcher_radarr_missing_search_retry_delay_minutes",
        "fetcher_radarr_missing_search_schedule_enabled",
        "fetcher_radarr_upgrade_search_max_items_per_run",
        "fetcher_radarr_upgrade_search_retry_delay_minutes",
        "fetcher_radarr_upgrade_search_schedule_enabled",
    }
    missing = required - names
    assert not missing, f"MediaMopSettings missing ADR-0009 fields: {sorted(missing)}"
    assert "fetcher_sonarr_search_retry_delay_minutes" not in names
    assert "fetcher_radarr_search_retry_delay_minutes" not in names
    assert "fetcher_sonarr_missing_search_enabled" in names
    assert "fetcher_sonarr_search_missing_enabled" not in names


def test_refiner_supplied_payload_evaluation_has_distinct_schedule_surface_on_settings() -> None:
    """ADR-0009 Refiner row: supplied payload evaluation owns its own schedule flags on the aggregate."""

    names = _field_names()
    assert "refiner_supplied_payload_evaluation_schedule_enabled" in names
    assert "refiner_supplied_payload_evaluation_schedule_interval_seconds" in names


def test_refiner_watched_folder_scan_dispatch_has_distinct_schedule_surface_on_settings() -> None:
    """Watched-folder scan periodic enqueue must not reuse supplied-payload schedule fields."""

    names = _field_names()
    assert "refiner_watched_folder_remux_scan_dispatch_schedule_enabled" in names
    assert "refiner_watched_folder_remux_scan_dispatch_schedule_interval_seconds" in names
    assert "refiner_watched_folder_remux_scan_dispatch_periodic_enqueue_remux_jobs" in names


def test_refiner_movie_output_cleanup_has_distinct_age_surface_on_settings() -> None:
    """Movies output-folder cleanup age gate must not reuse watched-folder min-age or work/temp stale fields."""

    names = _field_names()
    assert "refiner_movie_output_cleanup_min_age_seconds" in names


def test_refiner_tv_output_cleanup_has_distinct_age_surface_on_settings() -> None:
    """TV output-folder cleanup age gate must not reuse Movies output, watched-folder min-age, or work/temp stale fields."""

    names = _field_names()
    assert "refiner_tv_output_cleanup_min_age_seconds" in names


def test_refiner_work_temp_stale_sweep_has_distinct_schedule_surface_on_settings() -> None:
    """Work/temp stale sweep must not reuse watched-folder scan or supplied-payload schedule fields."""

    names = _field_names()
    assert "refiner_work_temp_stale_sweep_movie_schedule_enabled" in names
    assert "refiner_work_temp_stale_sweep_movie_schedule_interval_seconds" in names
    assert "refiner_work_temp_stale_sweep_tv_schedule_enabled" in names
    assert "refiner_work_temp_stale_sweep_tv_schedule_interval_seconds" in names
    assert "refiner_work_temp_stale_sweep_min_stale_age_seconds" in names
