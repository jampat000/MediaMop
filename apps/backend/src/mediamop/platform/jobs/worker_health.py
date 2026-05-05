"""In-memory worker heartbeat registry for background job lanes."""

from __future__ import annotations

import time
from dataclasses import dataclass
from threading import RLock

WORKER_HEARTBEAT_STALE_SECONDS = 360.0


@dataclass(frozen=True, slots=True)
class WorkerLaneHealth:
    module: str
    expected_workers: int
    active_workers: int
    stale_workers: int
    stopped_workers: int
    status: str
    detail: str


@dataclass(slots=True)
class _WorkerHeartbeat:
    module: str
    index: int
    started_at: float
    last_seen_at: float
    status: str = "running"


_lock = RLock()
_heartbeats: dict[tuple[str, int], _WorkerHeartbeat] = {}


def worker_started(module: str, index: int) -> None:
    now = time.monotonic()
    with _lock:
        _heartbeats[(module, int(index))] = _WorkerHeartbeat(
            module=module,
            index=int(index),
            started_at=now,
            last_seen_at=now,
        )


def worker_heartbeat(module: str, index: int) -> None:
    now = time.monotonic()
    key = (module, int(index))
    with _lock:
        row = _heartbeats.get(key)
        if row is None:
            _heartbeats[key] = _WorkerHeartbeat(module=module, index=int(index), started_at=now, last_seen_at=now)
        else:
            row.last_seen_at = now
            row.status = "running"


def worker_stopped(module: str, index: int) -> None:
    now = time.monotonic()
    key = (module, int(index))
    with _lock:
        row = _heartbeats.get(key)
        if row is None:
            _heartbeats[key] = _WorkerHeartbeat(
                module=module,
                index=int(index),
                started_at=now,
                last_seen_at=now,
                status="stopped",
            )
        else:
            row.last_seen_at = now
            row.status = "stopped"


def reset_worker_health_for_tests() -> None:
    with _lock:
        _heartbeats.clear()


def build_worker_health_snapshot(
    *,
    expected_workers: dict[str, int],
    stale_after_seconds: float = WORKER_HEARTBEAT_STALE_SECONDS,
) -> list[WorkerLaneHealth]:
    now = time.monotonic()
    lanes: list[WorkerLaneHealth] = []
    with _lock:
        rows = list(_heartbeats.values())
    for module, expected_raw in expected_workers.items():
        expected = max(0, int(expected_raw))
        module_rows = [row for row in rows if row.module == module and row.index < expected]
        if expected == 0:
            lanes.append(
                WorkerLaneHealth(
                    module=module,
                    expected_workers=0,
                    active_workers=0,
                    stale_workers=0,
                    stopped_workers=0,
                    status="disabled",
                    detail=f"{module.title()} workers are disabled by configuration.",
                ),
            )
            continue
        active = sum(1 for row in module_rows if row.status == "running" and now - row.last_seen_at <= stale_after_seconds)
        stale = sum(1 for row in module_rows if row.status == "running" and now - row.last_seen_at > stale_after_seconds)
        stopped = sum(1 for row in module_rows if row.status == "stopped")
        missing = max(0, expected - len(module_rows))
        degraded = stale + stopped + missing
        if degraded:
            detail = (
                f"{module.title()} expected {expected} worker(s), but "
                f"{degraded} are stale, stopped, or missing."
            )
            status = "degraded"
        else:
            detail = f"{module.title()} worker heartbeats are current."
            status = "healthy"
        lanes.append(
            WorkerLaneHealth(
                module=module,
                expected_workers=expected,
                active_workers=active,
                stale_workers=stale + missing,
                stopped_workers=stopped,
                status=status,
                detail=detail,
            ),
        )
    return lanes
