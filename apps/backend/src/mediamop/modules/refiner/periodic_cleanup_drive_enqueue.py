"""Refiner-local periodic enqueue for *arr live cleanup drive jobs (Pass 16).

Each :func:`run_periodic_refiner_cleanup_drive_enqueue` coroutine is a **separate** asyncio task
with its own interval — not a global Refiner scheduler gate. Lifespan starts one task per
enabled app (Radarr vs Sonarr) independently.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.jobs_model import RefinerJob
from mediamop.modules.refiner.radarr_failed_import_cleanup_job import (
    enqueue_radarr_failed_import_cleanup_drive_job,
)
from mediamop.modules.refiner.sonarr_failed_import_cleanup_job import (
    enqueue_sonarr_failed_import_cleanup_drive_job,
)

logger = logging.getLogger(__name__)

REFINER_SCHEDULE_ENQUEUE_FAILURE_COOLDOWN_SECONDS = 2.0

ScheduleSpec = tuple[str, float, Callable[[Session], RefinerJob]]


def refiner_cleanup_drive_enqueue_schedule_specs(
    settings: MediaMopSettings,
) -> list[ScheduleSpec]:
    """Return (log_label, interval_seconds, enqueue_fn) for each independently enabled schedule."""

    specs: list[ScheduleSpec] = []
    if settings.refiner_radarr_cleanup_drive_schedule_enabled:
        specs.append(
            (
                "radarr_failed_import_cleanup_drive",
                float(settings.refiner_radarr_cleanup_drive_schedule_interval_seconds),
                enqueue_radarr_failed_import_cleanup_drive_job,
            ),
        )
    if settings.refiner_sonarr_cleanup_drive_schedule_enabled:
        specs.append(
            (
                "sonarr_failed_import_cleanup_drive",
                float(settings.refiner_sonarr_cleanup_drive_schedule_interval_seconds),
                enqueue_sonarr_failed_import_cleanup_drive_job,
            ),
        )
    return specs


def start_refiner_cleanup_drive_enqueue_schedule_tasks(
    session_factory: sessionmaker[Session],
    settings: MediaMopSettings,
    *,
    stop_event: asyncio.Event,
) -> list[asyncio.Task[None]]:
    """Create one asyncio task per enabled cleanup-drive enqueue schedule (Radarr/Sonarr separate)."""

    tasks: list[asyncio.Task[None]] = []
    for label, interval_seconds, enqueue_fn in refiner_cleanup_drive_enqueue_schedule_specs(settings):
        tasks.append(
            asyncio.create_task(
                run_periodic_refiner_cleanup_drive_enqueue(
                    session_factory,
                    stop_event=stop_event,
                    interval_seconds=interval_seconds,
                    log_label=label,
                    enqueue_fn=enqueue_fn,
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
) -> None:
    """Enqueue on a fixed interval until *stop_event* is set (uses existing deduping enqueue)."""

    loop = asyncio.get_running_loop()
    while not stop_event.is_set():

        def _enqueue_once() -> None:
            with session_factory() as session:
                enqueue_fn(session)
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
