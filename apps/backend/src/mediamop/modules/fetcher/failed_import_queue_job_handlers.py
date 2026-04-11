"""Build Fetcher worker handler map for failed-import cleanup drives (composition root)."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.fetcher.fetcher_worker_loop import FetcherJobWorkContext
from mediamop.modules.fetcher.failed_import_drive_job_kinds import (
    FETCHER_FAILED_IMPORT_DRIVE_JOB_KINDS,
)
from mediamop.modules.fetcher.radarr_failed_import_cleanup_job import (
    FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE,
    make_radarr_failed_import_cleanup_drive_handler,
)
from mediamop.modules.fetcher.sonarr_failed_import_cleanup_job import (
    FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE,
    make_sonarr_failed_import_cleanup_drive_handler,
)
from mediamop.modules.queue_worker.failed_import_worker_ports import FailedImportQueueWorkerPorts


def build_failed_import_queue_job_handlers(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
    *,
    failed_import_runtime: FailedImportQueueWorkerPorts,
) -> Mapping[str, Callable[[FetcherJobWorkContext], None]]:
    """Handlers Fetcher workers use for Radarr/Sonarr failed-import cleanup drive job kinds."""

    out: dict[str, Callable[[FetcherJobWorkContext], None]] = {
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
    if set(out) != FETCHER_FAILED_IMPORT_DRIVE_JOB_KINDS:
        msg = (
            "build_failed_import_queue_job_handlers registry drift: "
            f"expected keys {sorted(FETCHER_FAILED_IMPORT_DRIVE_JOB_KINDS)!r}, got {sorted(out)!r}"
        )
        raise RuntimeError(msg)
    return out
