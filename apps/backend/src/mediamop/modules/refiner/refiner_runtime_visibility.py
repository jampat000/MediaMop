"""Map :class:`~mediamop.core.config.MediaMopSettings` to a bounded Refiner-only runtime snapshot."""

from __future__ import annotations

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.schemas_refiner_runtime_visibility import RefinerRuntimeSettingsOut

_VISIBILITY_NOTE = (
    "Values reflect this API process startup configuration. They do not prove a worker is mid-job "
    "or that another process is not also using the same database file."
)

_SQLITE_THROUGHPUT_NOTE = (
    "MediaMop stores durable jobs on SQLite. Several Refiner workers can each claim a different "
    "refiner_jobs row, but the database still serializes writes, so raising the count may not "
    "speed things up proportionally and can add contention."
)

_CONFIGURATION_NOTE = (
    "Refiner concurrency is controlled by the Processing settings page. Set Files at once to 1 for one active "
    "Refiner file worker or up to 8 for parallel file work. No restart is needed after changing that setting."
)

_WORK_TEMP_STALE_SWEEP_PERIODIC_NOTE = (
    "Optional periodic enqueue for refiner.work_temp_stale_sweep.v1 is **per scope** (Movies vs TV): "
    "MEDIAMOP_REFINER_WORK_TEMP_STALE_SWEEP_MOVIE_SCHEDULE_ENABLED / "
    "MEDIAMOP_REFINER_WORK_TEMP_STALE_SWEEP_MOVIE_SCHEDULE_INTERVAL_SECONDS and "
    "MEDIAMOP_REFINER_WORK_TEMP_STALE_SWEEP_TV_SCHEDULE_ENABLED / "
    "MEDIAMOP_REFINER_WORK_TEMP_STALE_SWEEP_TV_SCHEDULE_INTERVAL_SECONDS in apps/backend/.env (Refiner-only). "
    "Legacy MEDIAMOP_REFINER_WORK_TEMP_STALE_SWEEP_SCHEDULE_ENABLED and "
    "MEDIAMOP_REFINER_WORK_TEMP_STALE_SWEEP_SCHEDULE_INTERVAL_SECONDS still apply to **both** scopes when the "
    "per-scope variables are unset. Each tick enqueues one durable job per enabled scope; a Movies remux pass "
    "does not block TV temp cleanup and vice versa. "
    "Minimum age before deletion (shared narrow exception): MEDIAMOP_REFINER_WORK_TEMP_STALE_SWEEP_MIN_STALE_AGE_SECONDS "
    "(default one day). Restart the API after changing any of these — values are read at process start only."
)

_MOVIE_OUTPUT_CLEANUP_NOTE = (
    "Movies output-folder cleanup (Pass 3a) after a successful Movies remux uses "
    "MEDIAMOP_REFINER_MOVIE_OUTPUT_CLEANUP_MIN_AGE_SECONDS in apps/backend/.env (default 48 hours, clamped 1h..30d). "
    "Radarr library paths are read live from Radarr before any delete. Restart the API after changing this value."
)

_TV_OUTPUT_CLEANUP_NOTE = (
    "TV output-folder cleanup (Pass 3b) after a successful TV remux uses "
    "MEDIAMOP_REFINER_TV_OUTPUT_CLEANUP_MIN_AGE_SECONDS in apps/backend/.env (default 48 hours, clamped 1h..30d). "
    "The age gate looks at direct-child episode media files in the season output folder only. "
    "Before any delete, Refiner reads Sonarr's saved episode file locations and skips removal if any kept library file "
    "still maps under that season output folder. Restart the API after changing this value."
)

_FAILURE_CLEANUP_NOTE = (
    "Refiner Pass 4 failed-remux cleanup sweep uses separate Movies and TV timers and grace periods in apps/backend/.env: "
    "MEDIAMOP_REFINER_MOVIE_FAILURE_CLEANUP_SCHEDULE_ENABLED / "
    "MEDIAMOP_REFINER_MOVIE_FAILURE_CLEANUP_SCHEDULE_INTERVAL_SECONDS / "
    "MEDIAMOP_REFINER_MOVIE_FAILURE_CLEANUP_GRACE_PERIOD_SECONDS and "
    "MEDIAMOP_REFINER_TV_FAILURE_CLEANUP_SCHEDULE_ENABLED / "
    "MEDIAMOP_REFINER_TV_FAILURE_CLEANUP_SCHEDULE_INTERVAL_SECONDS / "
    "MEDIAMOP_REFINER_TV_FAILURE_CLEANUP_GRACE_PERIOD_SECONDS. "
    "Only terminal failed remux rows are eligible, and failure age uses refiner_jobs.updated_at. Restart required."
)

_WATCHED_FOLDER_SCAN_PERIODIC_NOTE = (
    "Optional periodic enqueue for refiner.watched_folder.remux_scan_dispatch.v1 uses "
    "MEDIAMOP_REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_SCHEDULE_ENABLED and "
    "MEDIAMOP_REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_SCHEDULE_INTERVAL_SECONDS in apps/backend/.env "
    "(Refiner-only schedule). Each tick evaluates Movies and TV "
    "independently: when a scope has no pending/leased scan for that scope and its watched folder is saved, "
    "one periodic scan job is enqueued for that scope (still not a filesystem watcher). "
    "File-pass options for periodic ticks: "
    "MEDIAMOP_REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_PERIODIC_ENQUEUE_REMUX_JOBS. "
    "Restart the API after changing any of these — values are read at process start only."
)
_REFINER_PROBE_NOTE = (
    "Refiner ffprobe preflight depth: MEDIAMOP_REFINER_PROBE_SIZE_MB and "
    "MEDIAMOP_REFINER_ANALYZE_DURATION_SECONDS in apps/backend/.env (read at startup; restart required)."
)


def refiner_runtime_settings_from_settings(settings: MediaMopSettings) -> RefinerRuntimeSettingsOut:
    """Map loaded settings to a DTO (no DB reads; Refiner-owned semantics)."""

    n = settings.refiner_worker_count
    disabled = n == 0
    if disabled:
        summary = (
            "In-process Refiner workers are off (0). refiner_jobs rows stay queued until you set "
            "MEDIAMOP_REFINER_WORKER_COUNT to at least 1 and restart this API."
        )
    elif n == 1:
        summary = (
            "Refiner has one available refiner_jobs worker slot. The Processing settings page controls the active "
            "Files at once value."
        )
    else:
        summary = (
            f"{n} in-process Refiner worker slots are available. The Processing settings page decides how many of "
            "those refiner_jobs slots may process files at once; other module lanes use their own workers."
        )

    return RefinerRuntimeSettingsOut(
        in_process_refiner_worker_count=n,
        in_process_workers_disabled=disabled,
        in_process_workers_enabled=not disabled,
        worker_mode_summary=summary,
        sqlite_throughput_note=_SQLITE_THROUGHPUT_NOTE,
        configuration_note=_CONFIGURATION_NOTE,
        visibility_note=_VISIBILITY_NOTE,
        refiner_watched_folder_remux_scan_dispatch_schedule_enabled=(
            settings.refiner_watched_folder_remux_scan_dispatch_schedule_enabled
        ),
        refiner_watched_folder_remux_scan_dispatch_schedule_interval_seconds=(
            settings.refiner_watched_folder_remux_scan_dispatch_schedule_interval_seconds
        ),
        refiner_watched_folder_remux_scan_dispatch_periodic_enqueue_remux_jobs=(
            settings.refiner_watched_folder_remux_scan_dispatch_periodic_enqueue_remux_jobs
        ),
        refiner_probe_size_mb=settings.refiner_probe_size_mb,
        refiner_analyze_duration_seconds=settings.refiner_analyze_duration_seconds,
        refiner_watched_folder_min_file_age_seconds=settings.refiner_watched_folder_min_file_age_seconds,
        refiner_movie_output_cleanup_min_age_seconds=settings.refiner_movie_output_cleanup_min_age_seconds,
        movie_output_cleanup_configuration_note=_MOVIE_OUTPUT_CLEANUP_NOTE,
        refiner_tv_output_cleanup_min_age_seconds=settings.refiner_tv_output_cleanup_min_age_seconds,
        tv_output_cleanup_configuration_note=_TV_OUTPUT_CLEANUP_NOTE,
        watched_folder_scan_periodic_configuration_note=f"{_WATCHED_FOLDER_SCAN_PERIODIC_NOTE} {_REFINER_PROBE_NOTE}",
        refiner_work_temp_stale_sweep_movie_schedule_enabled=settings.refiner_work_temp_stale_sweep_movie_schedule_enabled,
        refiner_work_temp_stale_sweep_movie_schedule_interval_seconds=(
            settings.refiner_work_temp_stale_sweep_movie_schedule_interval_seconds
        ),
        refiner_work_temp_stale_sweep_tv_schedule_enabled=settings.refiner_work_temp_stale_sweep_tv_schedule_enabled,
        refiner_work_temp_stale_sweep_tv_schedule_interval_seconds=(
            settings.refiner_work_temp_stale_sweep_tv_schedule_interval_seconds
        ),
        refiner_work_temp_stale_sweep_min_stale_age_seconds=settings.refiner_work_temp_stale_sweep_min_stale_age_seconds,
        refiner_movie_failure_cleanup_schedule_enabled=settings.refiner_movie_failure_cleanup_schedule_enabled,
        refiner_movie_failure_cleanup_schedule_interval_seconds=settings.refiner_movie_failure_cleanup_schedule_interval_seconds,
        refiner_tv_failure_cleanup_schedule_enabled=settings.refiner_tv_failure_cleanup_schedule_enabled,
        refiner_tv_failure_cleanup_schedule_interval_seconds=settings.refiner_tv_failure_cleanup_schedule_interval_seconds,
        refiner_movie_failure_cleanup_grace_period_seconds=settings.refiner_movie_failure_cleanup_grace_period_seconds,
        refiner_tv_failure_cleanup_grace_period_seconds=settings.refiner_tv_failure_cleanup_grace_period_seconds,
        failure_cleanup_configuration_note=_FAILURE_CLEANUP_NOTE,
        work_temp_stale_sweep_periodic_configuration_note=_WORK_TEMP_STALE_SWEEP_PERIODIC_NOTE,
    )
