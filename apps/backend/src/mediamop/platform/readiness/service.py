"""Application readiness separate from liveness."""

from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any

from mediamop.platform.jobs.worker_health import build_worker_health_snapshot
from mediamop.platform.readiness.schemas import ReadinessResponse, ReadinessStep, ReadinessWorkerOut


def build_readiness(app_state: Any) -> ReadinessResponse:
    started_at = float(getattr(app_state, "startup_started_at", time.monotonic()))
    startup_seconds = max(0.0, time.monotonic() - started_at)
    session_factory = getattr(app_state, "session_factory", None)
    engine = getattr(app_state, "engine", None)
    startup_complete = bool(getattr(app_state, "startup_ready", False))
    settings = getattr(app_state, "settings", None)
    worker_health: list[ReadinessWorkerOut] = []
    workers_ready = startup_complete
    if settings is not None:
        snapshot = build_worker_health_snapshot(
            expected_workers={
                "refiner": int(settings.refiner_worker_count),
                "pruner": int(settings.pruner_worker_count),
                "subber": int(settings.subber_worker_count),
            },
        )
        worker_health = [ReadinessWorkerOut(**asdict(row)) for row in snapshot]
        workers_ready = startup_complete and all(row.status in {"healthy", "disabled"} for row in snapshot)

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
            status="ready" if workers_ready else ("starting" if not startup_complete else "failed"),
            detail=(
                "Background workers and schedules are ready."
                if workers_ready
                else "One or more background workers are stale or stopped."
                if startup_complete
                else "MediaMop is starting background workers and schedules."
            ),
        ),
    ]
    ready = all(step.status == "ready" for step in steps)
    status = "ready" if ready else "failed" if any(step.status == "failed" for step in steps) else "starting"
    return ReadinessResponse(
        ready=ready,
        status=status,
        startup_seconds=round(startup_seconds, 3),
        steps=steps,
        worker_health=worker_health,
    )
