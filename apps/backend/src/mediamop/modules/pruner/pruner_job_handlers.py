"""Composition-root Pruner worker handler registry (``pruner_jobs`` families only)."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.queue_worker.job_kind_boundaries import validate_pruner_worker_handler_registry
from mediamop.modules.pruner.worker_loop import PrunerJobWorkContext


def build_pruner_job_handlers(
    _settings: MediaMopSettings,
    _session_factory: sessionmaker[Session],
) -> dict[str, Callable[[PrunerJobWorkContext], None]]:
    """Handlers for Pruner durable families (keys are ``pruner.*``). Phase 1: none shipped yet."""

    reg: dict[str, Callable[[PrunerJobWorkContext], None]] = {}
    validate_pruner_worker_handler_registry(reg)
    return reg
