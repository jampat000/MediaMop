"""Refiner-local periodic enqueue for *arr live cleanup drive jobs.

Each :func:`run_periodic_refiner_cleanup_drive_enqueue` coroutine is a **separate** asyncio task
with its own interval — not a global Refiner scheduler gate. Lifespan starts one task per
enabled schedule row supplied by the caller (Fetcher builds failed-import specs).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from mediamop.modules.refiner.failed_import_fetcher_runtime_ports import (
    FailedImportTimedSchedulePassQueuedPort,
    NoOpFailedImportTimedSchedulePassQueuedPort,
)
from mediamop.modules.refiner.jobs_model import RefinerJob

logger = logging.getLogger(__name__)

REFINER_SCHEDULE_ENQUEUE_FAILURE_COOLDOWN_SECONDS = 2.0

ScheduleSpec = tuple[str, float, Callable[[Session], RefinerJob]]

# Production schedule labels only — must stay aligned with dedupe keys in
# ``mediamop.modules.fetcher.radarr_failed_import_cleanup_job`` /
# ``sonarr_failed_import_cleanup_job`` (Fetcher-owned).
_SCHEDULE_PASS_QUEUED_META: dict[str, tuple[str, bool]] = {
    "radarr_failed_import_cleanup_drive": ("refiner.radarr.failed_import_cleanup_drive:v1", True),
    "sonarr_failed_import_cleanup_drive": ("refiner.sonarr.failed_import_cleanup_drive:v1", False),
}


def start_refiner_cleanup_drive_enqueue_schedule_tasks(
    session_factory: sessionmaker[Session],
    *,
    stop_event: asyncio.Event,
    timed_failed_import_pass_queued: FailedImportTimedSchedulePassQueuedPort,
    schedule_specs: list[ScheduleSpec],
) -> list[asyncio.Task[None]]:
    """Create one asyncio task per supplied cleanup-drive enqueue schedule (Radarr/Sonarr separate)."""

    tasks: list[asyncio.Task[None]] = []
    for label, interval_seconds, enqueue_fn in schedule_specs:
        tasks.append(
            asyncio.create_task(
                run_periodic_refiner_cleanup_drive_enqueue(
                    session_factory,
                    stop_event=stop_event,
                    interval_seconds=interval_seconds,
                    log_label=label,
                    enqueue_fn=enqueue_fn,
                    timed_failed_import_pass_queued=timed_failed_import_pass_queued,
                ),
                name=f"refiner-schedule-{label}",
            ),
        )
    return tasks


async def run_periodic_refiner_cleanup_drive_enqueue(
    session_factory: sessionmaker[Session],
    *,
    stop_event: asyncio.Event,
    interval_seconds: float,
    log_label: str,
    enqueue_fn: Callable[[Session], RefinerJob],
    timed_failed_import_pass_queued: FailedImportTimedSchedulePassQueuedPort | None = None,
) -> None:
    """Enqueue on a fixed interval until *stop_event* is set (uses existing deduping enqueue)."""

    pass_queued = (
        timed_failed_import_pass_queued
        if timed_failed_import_pass_queued is not None
        else NoOpFailedImportTimedSchedulePassQueuedPort()
    )

    loop = asyncio.get_running_loop()
    while not stop_event.is_set():

        def _enqueue_once() -> None:
            with session_factory() as session:
                meta = _SCHEDULE_PASS_QUEUED_META.get(log_label)
                existed_before = False
                if meta is not None:
                    dedupe_key, _movies = meta
                    existed_before = (
                        session.scalars(
                            select(RefinerJob.id).where(RefinerJob.dedupe_key == dedupe_key).limit(1),
                        ).first()
                        is not None
                    )
                enqueue_fn(session)
                if meta is not None and not existed_before:
                    _, movies = meta
                    pass_queued.record_timed_schedule_pass_queued_first_row(session, movies=movies)
                session.commit()

        try:
            await asyncio.to_thread(_enqueue_once)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Refiner periodic cleanup-drive enqueue failed label=%s", log_label)
            if stop_event.is_set():
                break
            fail_deadline = loop.time() + REFINER_SCHEDULE_ENQUEUE_FAILURE_COOLDOWN_SECONDS
            while loop.time() < fail_deadline and not stop_event.is_set():
                remaining = fail_deadline - loop.time()
                if remaining <= 0:
                    break
                await asyncio.sleep(min(0.25, remaining))
            continue

        if stop_event.is_set():
            break

        deadline = loop.time() + interval_seconds
        while loop.time() < deadline and not stop_event.is_set():
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            await asyncio.sleep(min(0.25, remaining))


async def stop_refiner_cleanup_drive_enqueue_schedule_tasks(
    tasks: list[asyncio.Task[None]],
) -> None:
    for t in tasks:
        if not t.done():
            t.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
