"""Map :class:`~mediamop.core.config.MediaMopSettings` to a bounded, read-only failed-import settings snapshot."""

from __future__ import annotations

from mediamop.core.config import MediaMopSettings
from mediamop.modules.fetcher.schemas_failed_import_runtime_visibility import FailedImportRuntimeVisibilityOut

_VISIBILITY_NOTE = (
    "Saved preferences when this loaded. Not a live status panel for your apps or for sweeps that may be running."
)


def failed_import_runtime_visibility_from_settings(settings: MediaMopSettings) -> FailedImportRuntimeVisibilityOut:
    """Map loaded settings to a bounded DTO (no DB reads; no liveness)."""

    n = settings.refiner_worker_count
    disabled = n == 0
    if disabled:
        summary = "Background automation is off — scheduled failed-import sweeps will not start by themselves."
    elif n == 1:
        summary = "One background automation slot is enabled (typical for a single-server setup)."
    else:
        summary = (
            f"Several background automation slots are enabled ({n}). On one database this is unusual — "
            "confirm it is what you want before relying on it."
        )

    return FailedImportRuntimeVisibilityOut(
        background_job_worker_count=n,
        in_process_workers_disabled=disabled,
        in_process_workers_enabled=not disabled,
        worker_mode_summary=summary,
        failed_import_radarr_cleanup_drive_schedule_enabled=(
            settings.failed_import_radarr_cleanup_drive_schedule_enabled
        ),
        failed_import_radarr_cleanup_drive_schedule_interval_seconds=(
            settings.failed_import_radarr_cleanup_drive_schedule_interval_seconds
        ),
        failed_import_sonarr_cleanup_drive_schedule_enabled=(
            settings.failed_import_sonarr_cleanup_drive_schedule_enabled
        ),
        failed_import_sonarr_cleanup_drive_schedule_interval_seconds=(
            settings.failed_import_sonarr_cleanup_drive_schedule_interval_seconds
        ),
        visibility_note=_VISIBILITY_NOTE,
    )
