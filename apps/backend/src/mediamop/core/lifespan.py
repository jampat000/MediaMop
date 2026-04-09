"""Application lifespan — wiring only; no business logic."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from mediamop.core.config import MediaMopSettings
from mediamop.core.db import (
    create_db_engine,
    create_session_factory,
    dispose_engine,
)
from mediamop.core.logging import configure_logging
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
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    try:
        yield
    finally:
        dispose_engine(app.state.engine)
        app.state.engine = None
        app.state.session_factory = None
