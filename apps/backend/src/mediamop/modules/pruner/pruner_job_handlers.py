"""Composition-root Pruner worker handler registry (``pruner_jobs`` families only)."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.queue_worker.job_kind_boundaries import validate_pruner_worker_handler_registry
from mediamop.modules.pruner.pruner_connection_job_handler import make_pruner_server_connection_test_handler
from mediamop.modules.pruner.pruner_apply_job_handler import make_pruner_candidate_removal_apply_handler
from mediamop.modules.pruner.pruner_job_kinds import (
    PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND,
    PRUNER_CANDIDATE_REMOVAL_PLEX_LIVE_JOB_KIND,
    PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND,
    PRUNER_SERVER_CONNECTION_TEST_JOB_KIND,
)
from mediamop.modules.pruner.pruner_plex_live_job_handler import make_pruner_plex_live_removal_handler
from mediamop.modules.pruner.pruner_preview_job_handler import make_pruner_candidate_removal_preview_handler
from mediamop.modules.pruner.worker_loop import PrunerJobWorkContext


def build_pruner_job_handlers(
    settings: MediaMopSettings,
    session_factory: sessionmaker[Session],
) -> dict[str, Callable[[PrunerJobWorkContext], None]]:
    """Handlers for Pruner durable families (keys are ``pruner.*``)."""

    reg: dict[str, Callable[[PrunerJobWorkContext], None]] = {
        PRUNER_SERVER_CONNECTION_TEST_JOB_KIND: make_pruner_server_connection_test_handler(
            settings,
            session_factory,
        ),
        PRUNER_CANDIDATE_REMOVAL_PREVIEW_JOB_KIND: make_pruner_candidate_removal_preview_handler(
            settings,
            session_factory,
        ),
        PRUNER_CANDIDATE_REMOVAL_APPLY_JOB_KIND: make_pruner_candidate_removal_apply_handler(
            settings,
            session_factory,
        ),
        PRUNER_CANDIDATE_REMOVAL_PLEX_LIVE_JOB_KIND: make_pruner_plex_live_removal_handler(
            settings,
            session_factory,
        ),
    }
    validate_pruner_worker_handler_registry(reg)
    return reg
