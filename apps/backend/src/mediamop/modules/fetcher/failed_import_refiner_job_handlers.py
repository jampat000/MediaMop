"""Build Refiner worker handler map for Fetcher failed-import cleanup drives (composition root)."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.fetcher.radarr_failed_import_cleanup_job import (
    REFINER_JOB_KIND_RADARR_FAILED_IMPORT_CLEANUP_DRIVE,
    make_radarr_failed_import_cleanup_drive_handler,
)
from mediamop.modules.fetcher.sonarr_failed_import_cleanup_job import (
    REFINER_JOB_KIND_SONARR_FAILED_IMPORT_CLEANUP_DRIVE,
    make_sonarr_failed_import_cleanup_drive_handler,
)
from mediamop.modules.refiner.failed_import_fetcher_runtime_ports import FailedImportRefinerRuntimeBundle
from mediamop.modules.refiner.worker_loop import RefinerJobWorkContext


def build_failed_import_refiner_job_handlers(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
    *,
    failed_import_runtime: FailedImportRefinerRuntimeBundle,
) -> Mapping[str, Callable[[RefinerJobWorkContext], None]]:
    """Handlers Refiner workers use for Radarr/Sonarr failed-import cleanup drive job kinds."""

    return {
        REFINER_JOB_KIND_RADARR_FAILED_IMPORT_CLEANUP_DRIVE: make_radarr_failed_import_cleanup_drive_handler(
            settings,
            session_factory,
            fetcher_runtime=failed_import_runtime.radarr_worker,
        ),
        REFINER_JOB_KIND_SONARR_FAILED_IMPORT_CLEANUP_DRIVE: make_sonarr_failed_import_cleanup_drive_handler(
            settings,
            session_factory,
            fetcher_runtime=failed_import_runtime.sonarr_worker,
        ),
    }
