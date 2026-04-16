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
    "Change MEDIAMOP_REFINER_WORKER_COUNT in apps/backend/.env (integer 0–8: 0 = off, 1 = one worker, "
    "2–8 = several concurrent workers for this Refiner lane only), then restart the MediaMop API."
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

_WATCHED_FOLDER_SCAN_PERIODIC_NOTE = (
    "Optional periodic enqueue for refiner.watched_folder.remux_scan_dispatch.v1 uses "
    "MEDIAMOP_REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_SCHEDULE_ENABLED and "
    "MEDIAMOP_REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_SCHEDULE_INTERVAL_SECONDS in apps/backend/.env "
    "(Refiner-only; not shared with Fetcher schedules). Each tick evaluates Movies and TV "
    "independently: when a scope has no pending/leased scan for that scope and its watched folder is saved, "
    "one periodic scan job is enqueued for that scope (still not a filesystem watcher). "
    "File-pass options for periodic ticks: "
    "MEDIAMOP_REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_PERIODIC_ENQUEUE_REMUX_JOBS and "
    "MEDIAMOP_REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_PERIODIC_REMUX_DRY_RUN. "
    "Restart the API after changing any of these — values are read at process start only."
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
            "One in-process Refiner worker is configured — it processes refiner_jobs one lease at a time "
            "(the usual default when automation is on)."
        )
    else:
        summary = (
            f"{n} in-process Refiner workers are configured — each can lease a different refiner_jobs row. "
            "Only this lane’s worker count is controlled here; other module lanes use their own settings."
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
        refiner_watched_folder_remux_scan_dispatch_periodic_remux_dry_run=(
            settings.refiner_watched_folder_remux_scan_dispatch_periodic_remux_dry_run
        ),
        refiner_watched_folder_min_file_age_seconds=settings.refiner_watched_folder_min_file_age_seconds,
        refiner_movie_output_cleanup_min_age_seconds=settings.refiner_movie_output_cleanup_min_age_seconds,
        movie_output_cleanup_configuration_note=_MOVIE_OUTPUT_CLEANUP_NOTE,
        watched_folder_scan_periodic_configuration_note=_WATCHED_FOLDER_SCAN_PERIODIC_NOTE,
        refiner_work_temp_stale_sweep_movie_schedule_enabled=settings.refiner_work_temp_stale_sweep_movie_schedule_enabled,
        refiner_work_temp_stale_sweep_movie_schedule_interval_seconds=(
            settings.refiner_work_temp_stale_sweep_movie_schedule_interval_seconds
        ),
        refiner_work_temp_stale_sweep_tv_schedule_enabled=settings.refiner_work_temp_stale_sweep_tv_schedule_enabled,
        refiner_work_temp_stale_sweep_tv_schedule_interval_seconds=(
            settings.refiner_work_temp_stale_sweep_tv_schedule_interval_seconds
        ),
        refiner_work_temp_stale_sweep_min_stale_age_seconds=settings.refiner_work_temp_stale_sweep_min_stale_age_seconds,
        work_temp_stale_sweep_periodic_configuration_note=_WORK_TEMP_STALE_SWEEP_PERIODIC_NOTE,
    )
