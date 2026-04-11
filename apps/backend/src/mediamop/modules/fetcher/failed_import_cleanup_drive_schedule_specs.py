"""Failed-import timed schedule rows for Refiner periodic enqueue (Fetcher-owned work, Refiner transport)."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from mediamop.core.config import MediaMopSettings
from mediamop.modules.fetcher.radarr_failed_import_cleanup_job import (
    enqueue_radarr_failed_import_cleanup_drive_job,
)
from mediamop.modules.fetcher.sonarr_failed_import_cleanup_job import (
    enqueue_sonarr_failed_import_cleanup_drive_job,
)
from mediamop.modules.refiner.jobs_model import RefinerJob
from mediamop.modules.refiner.periodic_cleanup_drive_enqueue import ScheduleSpec


def failed_import_cleanup_drive_schedule_specs(settings: MediaMopSettings) -> list[ScheduleSpec]:
    """Return (log_label, interval_seconds, enqueue_fn) for each independently enabled failed-import schedule."""

    specs: list[ScheduleSpec] = []
    if settings.failed_import_radarr_cleanup_drive_schedule_enabled:
        specs.append(
            (
                "radarr_failed_import_cleanup_drive",
                float(settings.failed_import_radarr_cleanup_drive_schedule_interval_seconds),
                enqueue_radarr_failed_import_cleanup_drive_job,
            ),
        )
    if settings.failed_import_sonarr_cleanup_drive_schedule_enabled:
        specs.append(
            (
                "sonarr_failed_import_cleanup_drive",
                float(settings.failed_import_sonarr_cleanup_drive_schedule_interval_seconds),
                enqueue_sonarr_failed_import_cleanup_drive_job,
            ),
        )
    return specs
