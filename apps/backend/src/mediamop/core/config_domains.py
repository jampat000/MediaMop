"""Domain-specific settings views for MediaMop runtime configuration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SessionSettings:
    secret: str | None
    cookie_name: str
    cookie_secure: bool
    cookie_samesite: str
    idle_minutes: int
    absolute_days: int


@dataclass(frozen=True, slots=True)
class AuthSettings:
    login_rate_max_attempts: int
    login_rate_window_seconds: int
    bootstrap_rate_max_attempts: int
    bootstrap_rate_window_seconds: int


@dataclass(frozen=True, slots=True)
class SecuritySettings:
    enable_hsts: bool
    cors_origins: tuple[str, ...]
    trusted_browser_origins_override: tuple[str, ...]
    trusted_proxy_ips: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RefinerSettings:
    worker_count: int
    supplied_payload_evaluation_schedule_enabled: bool
    supplied_payload_evaluation_schedule_interval_seconds: int
    watched_folder_remux_scan_dispatch_schedule_enabled: bool
    watched_folder_remux_scan_dispatch_schedule_interval_seconds: int
    watched_folder_remux_scan_dispatch_periodic_enqueue_remux_jobs: bool
    probe_size_mb: int
    analyze_duration_seconds: int
    watched_folder_min_file_age_seconds: int
    movie_output_cleanup_min_age_seconds: int
    tv_output_cleanup_min_age_seconds: int
    work_temp_stale_sweep_movie_schedule_enabled: bool
    work_temp_stale_sweep_movie_schedule_interval_seconds: int
    work_temp_stale_sweep_tv_schedule_enabled: bool
    work_temp_stale_sweep_tv_schedule_interval_seconds: int
    work_temp_stale_sweep_min_stale_age_seconds: int
    movie_failure_cleanup_schedule_enabled: bool
    movie_failure_cleanup_schedule_interval_seconds: int
    tv_failure_cleanup_schedule_enabled: bool
    tv_failure_cleanup_schedule_interval_seconds: int
    movie_failure_cleanup_grace_period_seconds: int
    tv_failure_cleanup_grace_period_seconds: int
    remux_media_root: str | None


@dataclass(frozen=True, slots=True)
class PrunerSettings:
    worker_count: int
    preview_schedule_enqueue_enabled: bool
    preview_schedule_scan_interval_seconds: int
    apply_enabled: bool
    plex_live_removal_enabled: bool
    plex_live_abs_max_items: int


@dataclass(frozen=True, slots=True)
class SubberSettings:
    worker_count: int
    library_scan_schedule_enqueue_enabled: bool
    library_scan_schedule_scan_interval_seconds: int
    upgrade_schedule_enqueue_enabled: bool


@dataclass(frozen=True, slots=True)
class ArrSettings:
    radarr_base_url: str | None
    radarr_api_key: str | None
    sonarr_base_url: str | None
    sonarr_api_key: str | None
