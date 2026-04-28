"""Application lifespan — wiring only; no business logic."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from mediamop.core.alembic_revision_check import ensure_database_at_application_head
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import (
    create_db_engine,
    create_session_factory,
    dispose_engine,
)
from mediamop.core.logging import configure_logging
from mediamop.modules.refiner.refiner_job_handlers import build_refiner_job_handlers
from mediamop.modules.refiner.refiner_operator_settings_service import ensure_refiner_operator_settings_row
from mediamop.modules.refiner.refiner_crash_recovery import cleanup_refiner_partial_output_files
from mediamop.modules.refiner.refiner_failure_cleanup_periodic_enqueue import (
    start_refiner_failure_cleanup_enqueue_tasks,
    stop_refiner_failure_cleanup_enqueue_tasks,
)
from mediamop.modules.subber.subber_job_handlers import build_subber_job_handlers
from mediamop.modules.subber.subber_schedule_enqueue import (
    start_subber_movies_scan_schedule_enqueue_tasks,
    start_subber_tv_scan_schedule_enqueue_tasks,
    start_subber_upgrade_schedule_enqueue_tasks,
    stop_subber_movies_scan_schedule_enqueue_tasks,
    stop_subber_tv_scan_schedule_enqueue_tasks,
    stop_subber_upgrade_schedule_enqueue_tasks,
)
from mediamop.modules.pruner.pruner_job_handlers import build_pruner_job_handlers
from mediamop.modules.refiner.refiner_supplied_payload_evaluation_periodic_enqueue import (
    start_refiner_supplied_payload_evaluation_enqueue_tasks,
    stop_refiner_supplied_payload_evaluation_enqueue_tasks,
)
from mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_periodic_enqueue import (
    start_refiner_watched_folder_remux_scan_dispatch_enqueue_tasks,
    stop_refiner_watched_folder_remux_scan_dispatch_enqueue_tasks,
)
from mediamop.modules.refiner.refiner_work_temp_stale_sweep_periodic_enqueue import (
    start_refiner_work_temp_stale_sweep_enqueue_tasks,
    stop_refiner_work_temp_stale_sweep_enqueue_tasks,
)
from mediamop.modules.refiner.worker_loop import (
    start_refiner_worker_background_tasks,
    stop_refiner_worker_background_tasks,
)
from mediamop.modules.subber.worker_loop import (
    start_subber_worker_background_tasks,
    stop_subber_worker_background_tasks,
)
from mediamop.modules.pruner.pruner_preview_schedule_enqueue import (
    start_pruner_preview_schedule_enqueue_tasks,
    stop_pruner_preview_schedule_enqueue_tasks,
)
from mediamop.modules.pruner.worker_loop import (
    start_pruner_worker_background_tasks,
    stop_pruner_worker_background_tasks,
)
from mediamop.platform.auth.rate_limit import SlidingWindowLimiter
from mediamop.platform.jobs.startup_recovery import recover_incomplete_jobs_after_startup
from mediamop.platform.suite_settings.logs_service import prune_logs_for_retention
from mediamop.platform.suite_settings.suite_configuration_backup_periodic import (
    start_suite_configuration_backup_tasks,
    stop_suite_configuration_backup_tasks,
)
from mediamop.platform.suite_settings.logs_retention_periodic import (
    start_log_retention_tasks,
    stop_log_retention_tasks,
)

_lifespan_log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.startup_started_at = time.monotonic()
    app.state.startup_ready = False
    settings = MediaMopSettings.load()
    app.state.settings = settings
    app.state.auth_login_rate_limiter = SlidingWindowLimiter(
        max_events=settings.auth_login_rate_max_attempts,
        window_seconds=float(settings.auth_login_rate_window_seconds),
    )
    app.state.bootstrap_rate_limiter = SlidingWindowLimiter(
        max_events=settings.bootstrap_rate_max_attempts,
        window_seconds=float(settings.bootstrap_rate_window_seconds),
    )
    configure_logging(settings)
    engine = create_db_engine(settings)
    ensure_database_at_application_head(engine)
    app.state.engine = engine
    session_factory = create_session_factory(engine)
    app.state.session_factory = session_factory
    with session_factory() as session:
        with session.begin():
            recovered = recover_incomplete_jobs_after_startup(session)
            partial_outputs_removed = cleanup_refiner_partial_output_files(session, settings)
            prune_logs_for_retention(session, settings)
        if recovered.total_recovered or partial_outputs_removed:
            _lifespan_log.warning(
                "MediaMop startup recovered interrupted work recovered_jobs=%s partial_outputs_removed=%s",
                recovered.as_log_dict(),
                partial_outputs_removed,
            )
    stop = asyncio.Event()
    log_retention_tasks = start_log_retention_tasks(
        session_factory,
        stop_event=stop,
        settings=settings,
    )
    refiner_supplied_payload_eval_tasks = start_refiner_supplied_payload_evaluation_enqueue_tasks(
        session_factory,
        stop_event=stop,
        settings=settings,
    )
    refiner_watched_folder_scan_dispatch_tasks = start_refiner_watched_folder_remux_scan_dispatch_enqueue_tasks(
        session_factory,
        stop_event=stop,
        settings=settings,
    )
    refiner_work_temp_stale_sweep_tasks = start_refiner_work_temp_stale_sweep_enqueue_tasks(
        session_factory,
        stop_event=stop,
        settings=settings,
    )
    refiner_failure_cleanup_tasks = start_refiner_failure_cleanup_enqueue_tasks(
        session_factory,
        stop_event=stop,
        settings=settings,
    )
    refiner_handlers = build_refiner_job_handlers(settings, session_factory)

    def _refiner_max_concurrent_files() -> int:
        with session_factory() as session:
            row = ensure_refiner_operator_settings_row(session)
            return max(1, min(8, int(row.max_concurrent_files)))

    refiner_stop, refiner_worker_tasks = start_refiner_worker_background_tasks(
        session_factory,
        settings,
        stop_event=stop,
        job_handlers=refiner_handlers,
        max_concurrent_files_getter=_refiner_max_concurrent_files,
    )
    pruner_handlers = build_pruner_job_handlers(settings, session_factory)
    pruner_preview_schedule_tasks = start_pruner_preview_schedule_enqueue_tasks(
        session_factory,
        stop_event=stop,
        settings=settings,
    )
    pruner_stop, pruner_worker_tasks = start_pruner_worker_background_tasks(
        session_factory,
        settings,
        stop_event=stop,
        job_handlers=pruner_handlers,
    )
    subber_handlers = build_subber_job_handlers(settings, session_factory)
    subber_tv_scan_tasks = start_subber_tv_scan_schedule_enqueue_tasks(
        session_factory,
        stop_event=stop,
        settings=settings,
    )
    subber_movies_scan_tasks = start_subber_movies_scan_schedule_enqueue_tasks(
        session_factory,
        stop_event=stop,
        settings=settings,
    )
    subber_upgrade_tasks = start_subber_upgrade_schedule_enqueue_tasks(
        session_factory,
        stop_event=stop,
        settings=settings,
    )
    subber_stop, subber_worker_tasks = start_subber_worker_background_tasks(
        session_factory,
        settings,
        stop_event=stop,
        job_handlers=subber_handlers,
    )
    suite_configuration_backup_tasks = start_suite_configuration_backup_tasks(
        session_factory,
        stop_event=stop,
        settings=settings,
    )
    app.state.startup_ready = True
    try:
        yield
    finally:
        app.state.startup_ready = False
        stop.set()
        await stop_refiner_supplied_payload_evaluation_enqueue_tasks(refiner_supplied_payload_eval_tasks)
        await stop_refiner_watched_folder_remux_scan_dispatch_enqueue_tasks(refiner_watched_folder_scan_dispatch_tasks)
        await stop_refiner_work_temp_stale_sweep_enqueue_tasks(refiner_work_temp_stale_sweep_tasks)
        await stop_refiner_failure_cleanup_enqueue_tasks(refiner_failure_cleanup_tasks)
        try:
            await stop_subber_tv_scan_schedule_enqueue_tasks(subber_tv_scan_tasks)
        except Exception:
            _lifespan_log.exception("Subber TV scan schedule enqueue stop failed")
        try:
            await stop_subber_movies_scan_schedule_enqueue_tasks(subber_movies_scan_tasks)
        except Exception:
            _lifespan_log.exception("Subber Movies scan schedule enqueue stop failed")
        try:
            await stop_subber_upgrade_schedule_enqueue_tasks(subber_upgrade_tasks)
        except Exception:
            _lifespan_log.exception("Subber upgrade schedule enqueue stop failed")
        await stop_suite_configuration_backup_tasks(suite_configuration_backup_tasks)
        await stop_log_retention_tasks(log_retention_tasks)
        await stop_subber_worker_background_tasks(subber_stop, subber_worker_tasks)
        await stop_pruner_preview_schedule_enqueue_tasks(pruner_preview_schedule_tasks)
        await stop_pruner_worker_background_tasks(pruner_stop, pruner_worker_tasks)
        await stop_refiner_worker_background_tasks(refiner_stop, refiner_worker_tasks)
        dispose_engine(app.state.engine)
        app.state.engine = None
        app.state.session_factory = None
