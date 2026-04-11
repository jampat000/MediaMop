"""Build Refiner worker handler map for Fetcher failed-import cleanup drives (composition root)."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.fetcher.radarr_failed_import_cleanup_job import (
    FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE,
    make_radarr_failed_import_cleanup_drive_handler,
)
from mediamop.modules.fetcher.sonarr_failed_import_cleanup_job import (
    FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE,
    make_sonarr_failed_import_cleanup_drive_handler,
)
from mediamop.modules.refiner.failed_import_queue_worker_ports import FailedImportQueueWorkerPorts
from mediamop.modules.refiner.worker_loop import RefinerJobWorkContext


def build_failed_import_queue_job_handlers(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
    *,
    failed_import_runtime: FailedImportQueueWorkerPorts,
) -> Mapping[str, Callable[[RefinerJobWorkContext], None]]:
    """Handlers Refiner workers use for Radarr/Sonarr failed-import cleanup drive job kinds."""

    return {
        FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE: make_radarr_failed_import_cleanup_drive_handler(
            settings,
            session_factory,
            fetcher_runtime=failed_import_runtime.radarr_worker,
        ),
        FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE: make_sonarr_failed_import_cleanup_drive_handler(
            settings,
            session_factory,
            fetcher_runtime=failed_import_runtime.sonarr_worker,
        ),
    }
