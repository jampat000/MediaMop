"""Composition-root Refiner worker handler registry (Refiner ``refiner_jobs`` families only)."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.queue_worker.job_kind_boundaries import validate_refiner_worker_handler_registry
from mediamop.modules.refiner.refiner_candidate_gate_handlers import make_refiner_candidate_gate_handler
from mediamop.modules.refiner.refiner_candidate_gate_job_kinds import REFINER_CANDIDATE_GATE_JOB_KIND
from mediamop.modules.refiner.refiner_library_audit_pass_handlers import (
    make_refiner_library_audit_pass_handler,
)
from mediamop.modules.refiner.refiner_library_audit_pass_job_kinds import (
    REFINER_LIBRARY_AUDIT_PASS_JOB_KIND,
)
from mediamop.modules.refiner.worker_loop import RefinerJobWorkContext


def build_refiner_job_handlers(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
) -> dict[str, Callable[[RefinerJobWorkContext], None]]:
    """Handlers for all production Refiner durable families (keys are ``refiner.*``)."""

    reg: dict[str, Callable[[RefinerJobWorkContext], None]] = {
        REFINER_LIBRARY_AUDIT_PASS_JOB_KIND: make_refiner_library_audit_pass_handler(session_factory),
        REFINER_CANDIDATE_GATE_JOB_KIND: make_refiner_candidate_gate_handler(settings, session_factory),
    }
    validate_refiner_worker_handler_registry(reg)
    return reg
