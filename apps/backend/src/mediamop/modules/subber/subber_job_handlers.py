"""Composition-root Subber worker handler registry (``subber_jobs`` families only)."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from mediamop.modules.queue_worker.job_kind_boundaries import validate_subber_worker_handler_registry
from mediamop.modules.subber.subber_supplied_cue_timeline_constraints_check_handlers import (
    make_subber_supplied_cue_timeline_constraints_check_handler,
)
from mediamop.modules.subber.subber_supplied_cue_timeline_constraints_check_job_kinds import (
    SUBBER_SUPPLIED_CUE_TIMELINE_CONSTRAINTS_CHECK_JOB_KIND,
)
from mediamop.modules.subber.worker_loop import SubberJobWorkContext


def build_subber_job_handlers(
    session_factory: sessionmaker[Session],
) -> dict[str, Callable[[SubberJobWorkContext], None]]:
    """Handlers for all production Subber durable families (keys are ``subber.*``)."""

    reg: dict[str, Callable[[SubberJobWorkContext], None]] = {
        SUBBER_SUPPLIED_CUE_TIMELINE_CONSTRAINTS_CHECK_JOB_KIND: (
            make_subber_supplied_cue_timeline_constraints_check_handler(session_factory)
        ),
    }
    validate_subber_worker_handler_registry(reg)
    return reg
