"""Composition-root Refiner worker handler registry (Refiner ``refiner_jobs`` families only)."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.refiner.file_remux_pass.handlers import make_refiner_file_remux_pass_handler
from mediamop.refiner.file_remux_pass.job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.refiner.job_kind_guard import validate_refiner_worker_handler_registry
from mediamop.refiner.refiner_failure_cleanup_handlers import make_refiner_failure_cleanup_handler
from mediamop.refiner.refiner_failure_cleanup_job_kinds import (
    REFINER_MOVIE_FAILURE_CLEANUP_SWEEP_JOB_KIND,
    REFINER_TV_FAILURE_CLEANUP_SWEEP_JOB_KIND,
)
from mediamop.refiner.refiner_pass_through import (
    REFINER_FILE_PASS_THROUGH_JOB_KIND,
    REFINER_FILE_REJECT_JOB_KIND,
    make_refiner_file_pass_through_handler,
)
from mediamop.refiner.refiner_reject import make_refiner_file_reject_handler
from mediamop.refiner.refiner_watched_folder_remux_scan_dispatch_handlers import (
    make_refiner_watched_folder_remux_scan_dispatch_handler,
)
from mediamop.refiner.refiner_watched_folder_remux_scan_dispatch_job_kinds import (
    REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND,
)
from mediamop.refiner.refiner_work_temp_stale_sweep_handlers import (
    make_refiner_work_temp_stale_sweep_handler,
)
from mediamop.refiner.refiner_work_temp_stale_sweep_job_kinds import (
    REFINER_WORK_TEMP_STALE_SWEEP_JOB_KIND,
)
from mediamop.refiner.worker_loop import RefinerJobWorkContext


def build_refiner_job_handlers(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
) -> dict[str, Callable[[RefinerJobWorkContext], None]]:
    """Handlers for all production Refiner durable families (keys are ``refiner.*``)."""

    reg: dict[str, Callable[[RefinerJobWorkContext], None]] = {
        REFINER_FILE_REMUX_PASS_JOB_KIND: make_refiner_file_remux_pass_handler(settings, session_factory),
        # Hands back the original when processing gave up, so a file is never stranded (#465).
        REFINER_FILE_PASS_THROUGH_JOB_KIND: make_refiner_file_pass_through_handler(settings, session_factory),
        # The opt-in reject policy; falls back to a pass-through whenever it cannot act safely (#471).
        REFINER_FILE_REJECT_JOB_KIND: make_refiner_file_reject_handler(settings, session_factory),
        REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_JOB_KIND: make_refiner_watched_folder_remux_scan_dispatch_handler(
            settings,
            session_factory,
        ),
        REFINER_WORK_TEMP_STALE_SWEEP_JOB_KIND: make_refiner_work_temp_stale_sweep_handler(settings, session_factory),
        REFINER_MOVIE_FAILURE_CLEANUP_SWEEP_JOB_KIND: make_refiner_failure_cleanup_handler(
            settings,
            session_factory,
            default_scope="movie",
        ),
        REFINER_TV_FAILURE_CLEANUP_SWEEP_JOB_KIND: make_refiner_failure_cleanup_handler(
            settings,
            session_factory,
            default_scope="tv",
        ),
    }
    validate_refiner_worker_handler_registry(reg)
    return reg
