"""Application readiness separate from liveness."""

from __future__ import annotations

import time
from typing import Any

from mediamop.platform.readiness.schemas import ReadinessResponse, ReadinessStep


def build_readiness(app_state: Any) -> ReadinessResponse:
    started_at = float(getattr(app_state, "startup_started_at", time.monotonic()))
    startup_seconds = max(0.0, time.monotonic() - started_at)
    session_factory = getattr(app_state, "session_factory", None)
    engine = getattr(app_state, "engine", None)
    startup_complete = bool(getattr(app_state, "startup_ready", False))

    steps = [
        ReadinessStep(
            name="database",
            status="ready" if session_factory is not None and engine is not None else "starting",
            detail=(
                "Local database is connected and migrations are complete."
                if session_factory is not None and engine is not None
                else "MediaMop is preparing the local database."
            ),
        ),
        ReadinessStep(
            name="workers",
            status="ready" if startup_complete else "starting",
            detail=(
                "Background workers and schedules are ready."
                if startup_complete
                else "MediaMop is starting background workers and schedules."
            ),
        ),
    ]
    ready = all(step.status == "ready" for step in steps)
    return ReadinessResponse(
        ready=ready,
        status="ready" if ready else "starting",
        startup_seconds=round(startup_seconds, 3),
        steps=steps,
    )
