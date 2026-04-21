"""Read-only Refiner runtime settings snapshot (from :class:`~mediamop.core.config.MediaMopSettings` at process start)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RefinerRuntimeSettingsOut(BaseModel):
    """What this API process was configured to run for ``refiner_jobs`` in-process workers only."""

    in_process_refiner_worker_count: int = Field(
        ge=0,
        le=8,
        description="Mirrors MEDIAMOP_REFINER_WORKER_COUNT after clamping — Refiner lane only.",
    )
    in_process_workers_disabled: bool = Field(
        description="True when worker count is 0 (no in-process Refiner worker tasks).",
    )
    in_process_workers_enabled: bool = Field(
        description="True when at least one in-process Refiner worker task is configured.",
    )
    worker_mode_summary: str = Field(
        description="Plain-language summary for 0 / 1 / >1 Refiner workers.",
    )
    sqlite_throughput_note: str = Field(
        description="Honest caveat about SQLite single-writer behavior when count > 1.",
    )
    configuration_note: str = Field(
        description="How operators change the value (env + restart); not an in-app editor.",
    )
    visibility_note: str = Field(
        description="Caveat: from settings loaded at startup — not a live probe of worker threads.",
    )
    refiner_watched_folder_remux_scan_dispatch_schedule_enabled: bool = Field(
        description="``MEDIAMOP_REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_SCHEDULE_ENABLED`` at process start.",
    )
    refiner_watched_folder_remux_scan_dispatch_schedule_interval_seconds: int = Field(
        ge=60,
        description="Seconds between periodic enqueue attempts (clamped 60..7d); restart required to change.",
    )
    refiner_watched_folder_remux_scan_dispatch_periodic_enqueue_remux_jobs: bool = Field(
        description="When true, periodic scans may enqueue ``refiner.file.remux_pass.v1``.",
    )
    refiner_probe_size_mb: int = Field(
        ge=1,
        le=1024,
        description="ffprobe probe size in MB for Refiner preflight analysis.",
    )
    refiner_analyze_duration_seconds: int = Field(
        ge=1,
        le=300,
        description="ffprobe analyze duration in seconds for Refiner preflight analysis.",
    )
    refiner_watched_folder_min_file_age_seconds: int = Field(
        ge=0,
        description="Minimum file age before watched-folder scan or one-file pass touches media.",
    )
    refiner_movie_output_cleanup_min_age_seconds: int = Field(
        ge=3600,
        description="Minimum age (newest file mtime under the folder) before Pass 3a may delete a Movies output folder (1h..30d; default 48h).",
    )
    movie_output_cleanup_configuration_note: str = Field(
        description="How operators change Movies output-folder cleanup age gate (restart required).",
    )
    refiner_tv_output_cleanup_min_age_seconds: int = Field(
        ge=3600,
        description="Minimum age (direct-child episode media newest mtime) before Pass 3b may delete a TV season output folder (1h..30d; default 48h).",
    )
    tv_output_cleanup_configuration_note: str = Field(
        description="How operators change TV output-folder cleanup age gate (restart required).",
    )
    watched_folder_scan_periodic_configuration_note: str = Field(
        description="How operators change periodic scan env (restart required).",
    )
    refiner_work_temp_stale_sweep_movie_schedule_enabled: bool = Field(
        description="``MEDIAMOP_REFINER_WORK_TEMP_STALE_SWEEP_MOVIE_SCHEDULE_ENABLED`` at process start.",
    )
    refiner_work_temp_stale_sweep_movie_schedule_interval_seconds: int = Field(
        ge=60,
        description="Seconds between Movies-only periodic stale temp sweep enqueue ticks (clamped 60..7d).",
    )
    refiner_work_temp_stale_sweep_tv_schedule_enabled: bool = Field(
        description="``MEDIAMOP_REFINER_WORK_TEMP_STALE_SWEEP_TV_SCHEDULE_ENABLED`` at process start.",
    )
    refiner_work_temp_stale_sweep_tv_schedule_interval_seconds: int = Field(
        ge=60,
        description="Seconds between TV-only periodic stale temp sweep enqueue ticks (clamped 60..7d).",
    )
    refiner_work_temp_stale_sweep_min_stale_age_seconds: int = Field(
        ge=60,
        description="Minimum file age before Refiner removes its own stale temp work files (60s..30d). "
        "Shared for both scopes (narrow exception: same temp filename semantics).",
    )
    refiner_movie_failure_cleanup_schedule_enabled: bool = Field(
        description="``MEDIAMOP_REFINER_MOVIE_FAILURE_CLEANUP_SCHEDULE_ENABLED`` at process start.",
    )
    refiner_movie_failure_cleanup_schedule_interval_seconds: int = Field(
        ge=60,
        description="Seconds between Movies-only periodic failed-remux cleanup enqueue ticks.",
    )
    refiner_tv_failure_cleanup_schedule_enabled: bool = Field(
        description="``MEDIAMOP_REFINER_TV_FAILURE_CLEANUP_SCHEDULE_ENABLED`` at process start.",
    )
    refiner_tv_failure_cleanup_schedule_interval_seconds: int = Field(
        ge=60,
        description="Seconds between TV-only periodic failed-remux cleanup enqueue ticks.",
    )
    refiner_movie_failure_cleanup_grace_period_seconds: int = Field(
        ge=300,
        le=604800,
        description="Failed remux age gate for Movies failure cleanup (uses refiner_jobs.updated_at).",
    )
    refiner_tv_failure_cleanup_grace_period_seconds: int = Field(
        ge=300,
        le=604800,
        description="Failed remux age gate for TV failure cleanup (uses refiner_jobs.updated_at).",
    )
    failure_cleanup_configuration_note: str = Field(
        description="How operators change Pass 4 failure-cleanup timers/grace (restart required).",
    )
    work_temp_stale_sweep_periodic_configuration_note: str = Field(
        description="How operators change work/temp stale sweep env (restart required).",
    )
