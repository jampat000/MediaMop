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
