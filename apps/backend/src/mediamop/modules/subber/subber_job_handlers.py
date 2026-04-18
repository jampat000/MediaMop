"""Composition-root Subber worker handler registry (``subber_jobs`` families only)."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.queue_worker.job_kind_boundaries import validate_subber_worker_handler_registry
from mediamop.modules.subber.subber_job_kinds import ALL_SUBBER_PRODUCTION_JOB_KINDS
from mediamop.modules.subber.subber_library_scan_job_handler import register_library_scan_handlers
from mediamop.modules.subber.subber_search_job_handler import register_subtitle_search_handlers
from mediamop.modules.subber.subber_webhook_import_job_handler import register_webhook_import_handlers
from mediamop.modules.subber.worker_loop import SubberJobWorkContext


def build_subber_job_handlers(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
) -> dict[str, Callable[[SubberJobWorkContext], None]]:
    """Handlers for all production Subber durable families (keys are ``subber.*``)."""

    reg: dict[str, Callable[[SubberJobWorkContext], None]] = {}
    reg.update(register_subtitle_search_handlers(settings, session_factory))
    reg.update(register_library_scan_handlers(session_factory))
    reg.update(register_webhook_import_handlers(session_factory))
    if set(reg) != ALL_SUBBER_PRODUCTION_JOB_KINDS:
        missing = sorted(ALL_SUBBER_PRODUCTION_JOB_KINDS - set(reg))
        extra = sorted(set(reg) - ALL_SUBBER_PRODUCTION_JOB_KINDS)
        msg = f"Subber handler registry mismatch: missing={missing!r} extra={extra!r}"
        raise ValueError(msg)
    validate_subber_worker_handler_registry(reg)
    return reg
