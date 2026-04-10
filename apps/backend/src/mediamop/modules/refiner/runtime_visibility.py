"""Map :class:`~mediamop.core.config.MediaMopSettings` to a bounded Refiner runtime visibility DTO.

No asyncio introspection — **configured intent** only, not proved task liveness.
"""

from __future__ import annotations

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.schemas_runtime_visibility import RefinerRuntimeVisibilityOut

_VISIBILITY_NOTE = (
    "Values reflect application settings at request time. They do not prove that asyncio worker or "
    "schedule tasks are running, healthy, or successfully connected to external services."
)


def refiner_runtime_visibility_from_settings(settings: MediaMopSettings) -> RefinerRuntimeVisibilityOut:
    """Map loaded settings to a bounded inspection DTO (Refiner-local; no DB)."""

    n = settings.refiner_worker_count
    disabled = n == 0
    if disabled:
        summary = (
            "In-process Refiner workers are disabled (refiner_worker_count=0). "
            "No background claim/execute tasks are intended."
        )
    elif n == 1:
        summary = (
            "Single in-process Refiner worker (supported default for SQLite-first deployments)."
        )
    else:
        summary = (
            f"Multiple in-process Refiner workers (refiner_worker_count={n}). "
            "This is a guarded capability under SQLite single-writer rules — not the normal "
            "recommended rollout; validate behavior before relying on it in production."
        )

    return RefinerRuntimeVisibilityOut(
        refiner_worker_count=n,
        in_process_workers_disabled=disabled,
        in_process_workers_enabled=not disabled,
        worker_mode_summary=summary,
        refiner_radarr_cleanup_drive_schedule_enabled=settings.refiner_radarr_cleanup_drive_schedule_enabled,
        refiner_radarr_cleanup_drive_schedule_interval_seconds=(
            settings.refiner_radarr_cleanup_drive_schedule_interval_seconds
        ),
        refiner_sonarr_cleanup_drive_schedule_enabled=settings.refiner_sonarr_cleanup_drive_schedule_enabled,
        refiner_sonarr_cleanup_drive_schedule_interval_seconds=(
            settings.refiner_sonarr_cleanup_drive_schedule_interval_seconds
        ),
        visibility_note=_VISIBILITY_NOTE,
    )
