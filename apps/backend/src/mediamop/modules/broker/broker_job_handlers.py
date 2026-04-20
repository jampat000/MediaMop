"""Composition-root Broker worker handler registry (``broker_jobs`` families only)."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.broker.broker_indexer_test_job_handler import register_indexer_test_handler
from mediamop.modules.broker.broker_job_context import BrokerJobWorkContext
from mediamop.modules.broker.broker_job_kinds import ALL_BROKER_PRODUCTION_JOB_KINDS
from mediamop.modules.broker.broker_sync_job_handler import register_broker_sync_handlers
from mediamop.modules.queue_worker.job_kind_boundaries import validate_broker_worker_handler_registry


def build_broker_job_handlers(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
) -> dict[str, Callable[[BrokerJobWorkContext], None]]:
    """Handlers for all production Broker durable families (keys are ``broker.*``)."""

    _ = settings
    reg: dict[str, Callable[[BrokerJobWorkContext], None]] = {}
    reg.update(register_broker_sync_handlers(session_factory))
    reg.update(register_indexer_test_handler(session_factory))
    if set(reg) != ALL_BROKER_PRODUCTION_JOB_KINDS:
        missing = sorted(ALL_BROKER_PRODUCTION_JOB_KINDS - set(reg))
        extra = sorted(set(reg) - ALL_BROKER_PRODUCTION_JOB_KINDS)
        msg = f"Broker handler registry mismatch: missing={missing!r} extra={extra!r}"
        raise ValueError(msg)
    validate_broker_worker_handler_registry(reg)
    return reg
