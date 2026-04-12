"""Composition-root Trimmer worker handler registry (``trimmer_jobs`` families only)."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.queue_worker.job_kind_boundaries import validate_trimmer_worker_handler_registry
from mediamop.modules.trimmer.trimmer_supplied_trim_plan_json_file_write_handlers import (
    make_trimmer_supplied_trim_plan_json_file_write_handler,
)
from mediamop.modules.trimmer.trimmer_supplied_trim_plan_json_file_write_job_kinds import (
    TRIMMER_SUPPLIED_TRIM_PLAN_JSON_FILE_WRITE_JOB_KIND,
)
from mediamop.modules.trimmer.trimmer_trim_plan_constraints_check_handlers import (
    make_trimmer_trim_plan_constraints_check_handler,
)
from mediamop.modules.trimmer.trimmer_trim_plan_constraints_check_job_kinds import (
    TRIMMER_TRIM_PLAN_CONSTRAINTS_CHECK_JOB_KIND,
)
from mediamop.modules.trimmer.worker_loop import TrimmerJobWorkContext


def build_trimmer_job_handlers(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
) -> dict[str, Callable[[TrimmerJobWorkContext], None]]:
    """Handlers for all production Trimmer durable families (keys are ``trimmer.*``)."""

    reg: dict[str, Callable[[TrimmerJobWorkContext], None]] = {
        TRIMMER_TRIM_PLAN_CONSTRAINTS_CHECK_JOB_KIND: make_trimmer_trim_plan_constraints_check_handler(
            session_factory,
        ),
        TRIMMER_SUPPLIED_TRIM_PLAN_JSON_FILE_WRITE_JOB_KIND: make_trimmer_supplied_trim_plan_json_file_write_handler(
            settings,
            session_factory,
        ),
    }
    validate_trimmer_worker_handler_registry(reg)
    return reg
