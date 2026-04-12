"""Application lifespan — wiring only; no business logic."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from mediamop.core.alembic_revision_check import ensure_database_at_application_head
from mediamop.core.config import MediaMopSettings
from mediamop.core.db import (
    create_db_engine,
    create_session_factory,
    dispose_engine,
)
from mediamop.core.logging import configure_logging
from mediamop.modules.fetcher.failed_import_cleanup_drive_schedule_specs import (
    failed_import_cleanup_drive_schedule_specs,
)
from mediamop.modules.fetcher.failed_import_queue_job_handlers import build_failed_import_queue_job_handlers
from mediamop.modules.fetcher.failed_import_queue_worker_runtime import build_failed_import_queue_worker_runtime_bundle
from mediamop.modules.fetcher.fetcher_arr_search_handlers import merge_fetcher_failed_import_and_search_handlers
from mediamop.modules.fetcher.fetcher_arr_search_periodic_enqueue import (
    start_fetcher_arr_search_enqueue_tasks,
    stop_fetcher_arr_search_enqueue_tasks,
)
from mediamop.modules.fetcher.fetcher_worker_loop import (
    start_fetcher_worker_background_tasks,
    stop_fetcher_worker_background_tasks,
)
from mediamop.modules.fetcher.periodic_failed_import_cleanup_enqueue import (
    start_fetcher_failed_import_cleanup_drive_enqueue_tasks,
    stop_fetcher_failed_import_cleanup_drive_enqueue_tasks,
)
from mediamop.modules.refiner.refiner_job_handlers import build_refiner_job_handlers
from mediamop.modules.refiner.refiner_library_audit_pass_periodic_enqueue import (
    start_refiner_library_audit_pass_enqueue_tasks,
    stop_refiner_library_audit_pass_enqueue_tasks,
)
from mediamop.modules.refiner.worker_loop import (
    start_refiner_worker_background_tasks,
    stop_refiner_worker_background_tasks,
)
from mediamop.platform.auth.rate_limit import SlidingWindowLimiter


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
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
    stop = asyncio.Event()
    failed_import_queue_worker_runtime = build_failed_import_queue_worker_runtime_bundle()
    schedule_specs = failed_import_cleanup_drive_schedule_specs(settings)
    fetcher_schedule_tasks = start_fetcher_failed_import_cleanup_drive_enqueue_tasks(
        session_factory,
        stop_event=stop,
        timed_failed_import_pass_queued=failed_import_queue_worker_runtime.timed_schedule_pass_queued,
        schedule_specs=schedule_specs,
    )
    failed_import_job_handlers = build_failed_import_queue_job_handlers(
        settings,
        session_factory,
        failed_import_runtime=failed_import_queue_worker_runtime,
    )
    fetcher_job_handlers = merge_fetcher_failed_import_and_search_handlers(
        failed_import_job_handlers,
        settings,
        session_factory,
    )
    fetcher_arr_search_tasks = start_fetcher_arr_search_enqueue_tasks(
        session_factory,
        stop_event=stop,
        settings=settings,
    )
    refiner_library_audit_tasks = start_refiner_library_audit_pass_enqueue_tasks(
        session_factory,
        stop_event=stop,
        settings=settings,
    )
    fetcher_stop, fetcher_worker_tasks = start_fetcher_worker_background_tasks(
        session_factory,
        settings,
        stop_event=stop,
        job_handlers=fetcher_job_handlers,
    )
    refiner_handlers = build_refiner_job_handlers(settings, session_factory)
    refiner_stop, refiner_worker_tasks = start_refiner_worker_background_tasks(
        session_factory,
        settings,
        stop_event=stop,
        job_handlers=refiner_handlers,
    )
    try:
        yield
    finally:
        stop.set()
        await stop_fetcher_arr_search_enqueue_tasks(fetcher_arr_search_tasks)
        await stop_refiner_library_audit_pass_enqueue_tasks(refiner_library_audit_tasks)
        await stop_fetcher_failed_import_cleanup_drive_enqueue_tasks(fetcher_schedule_tasks)
        await stop_fetcher_worker_background_tasks(fetcher_stop, fetcher_worker_tasks)
        await stop_refiner_worker_background_tasks(refiner_stop, refiner_worker_tasks)
        dispose_engine(app.state.engine)
        app.state.engine = None
        app.state.session_factory = None
