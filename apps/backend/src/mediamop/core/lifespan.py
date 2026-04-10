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
from mediamop.modules.refiner.periodic_cleanup_drive_enqueue import (
    start_refiner_cleanup_drive_enqueue_schedule_tasks,
    stop_refiner_cleanup_drive_enqueue_schedule_tasks,
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
    refiner_stop = asyncio.Event()
    refiner_schedule_tasks = start_refiner_cleanup_drive_enqueue_schedule_tasks(
        session_factory,
        settings,
        stop_event=refiner_stop,
    )
    refiner_stop, refiner_tasks = start_refiner_worker_background_tasks(
        session_factory,
        settings,
        stop_event=refiner_stop,
    )
    try:
        yield
    finally:
        # Refiner shutdown: signal cooperative exit first, then cancel stragglers.
        # Stop periodic enqueue tasks before workers so enqueuers do not add work while workers drain.
        refiner_stop.set()
        await stop_refiner_cleanup_drive_enqueue_schedule_tasks(refiner_schedule_tasks)
        await stop_refiner_worker_background_tasks(refiner_stop, refiner_tasks)
        dispose_engine(app.state.engine)
        app.state.engine = None
        app.state.session_factory = None
