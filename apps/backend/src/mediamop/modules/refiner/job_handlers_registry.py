"""Production Refiner job handler map — one entry per job kind (Pass 15: Radarr cleanup drive only)."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.radarr_failed_import_cleanup_job import (
    REFINER_JOB_KIND_RADARR_FAILED_IMPORT_CLEANUP_DRIVE,
    make_radarr_failed_import_cleanup_drive_handler,
)
from mediamop.modules.refiner.worker_loop import RefinerJobWorkContext


def build_production_refiner_job_handlers(
    settings: MediaMopSettings,
) -> Mapping[str, Callable[[RefinerJobWorkContext], None]]:
    """Handlers the asyncio Refiner workers use (Radarr-only until Sonarr is added in a later pass)."""

    return {
        REFINER_JOB_KIND_RADARR_FAILED_IMPORT_CLEANUP_DRIVE: make_radarr_failed_import_cleanup_drive_handler(
            settings,
        ),
    }
