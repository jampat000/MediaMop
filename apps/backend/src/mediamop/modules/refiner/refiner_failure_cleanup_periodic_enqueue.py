"""Periodic asyncio enqueue for Refiner Pass 4 failure-cleanup sweeps."""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.refiner_failure_cleanup_enqueue import enqueue_refiner_failure_cleanup_sweep_job
from mediamop.modules.refiner.refiner_failure_cleanup_activity import record_refiner_failure_cleanup_sweep_skipped

logger = logging.getLogger(__name__)

REFINER_FAILURE_CLEANUP_ENQUEUE_FAILURE_COOLDOWN_SECONDS = 2.0


def start_refiner_failure_cleanup_enqueue_tasks(
    session_factory: sessionmaker[Session],
    *,
    stop_event: asyncio.Event,
    settings: MediaMopSettings,
) -> list[asyncio.Task[None]]:
    tasks: list[asyncio.Task[None]] = []
    if settings.refiner_movie_failure_cleanup_schedule_enabled:
        iv = float(settings.refiner_movie_failure_cleanup_schedule_interval_seconds)
        if iv > 0:
            tasks.append(
                asyncio.create_task(
                    _run_periodic_scope_enqueue(
                        session_factory,
                        stop_event=stop_event,
                        interval_seconds=iv,
                        media_scope="movie",
                    ),
                    name="refiner-failure-cleanup-enqueue-movie",
                ),
            )
    if settings.refiner_tv_failure_cleanup_schedule_enabled:
        iv = float(settings.refiner_tv_failure_cleanup_schedule_interval_seconds)
        if iv > 0:
            tasks.append(
                asyncio.create_task(
                    _run_periodic_scope_enqueue(
                        session_factory,
                        stop_event=stop_event,
                        interval_seconds=iv,
                        media_scope="tv",
                    ),
                    name="refiner-failure-cleanup-enqueue-tv",
                ),
            )
    return tasks


async def _run_periodic_scope_enqueue(
    session_factory: sessionmaker[Session],
    *,
    stop_event: asyncio.Event,
    interval_seconds: float,
    media_scope: Literal["movie", "tv"],
) -> None:
    loop = asyncio.get_running_loop()
    while not stop_event.is_set():

        def _once() -> None:
            with session_factory() as session:
                job, inserted = enqueue_refiner_failure_cleanup_sweep_job(session, media_scope=media_scope)
                if not inserted:
                    record_refiner_failure_cleanup_sweep_skipped(
                        session,
                        media_scope=media_scope,
                        detail=(
                            f'{{"media_scope":"{media_scope}","cleanup_run_status":"skipped",'
                            f'"reason":"Previous cleanup job is still queued or running.",'
                            f'"existing_job_id":{int(job.id)}}}'
                        ),
                    )
                session.commit()

        try:
            await asyncio.to_thread(_once)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Refiner failure cleanup periodic enqueue failed (media_scope=%s)", media_scope)
            if stop_event.is_set():
                break
            fail_deadline = loop.time() + REFINER_FAILURE_CLEANUP_ENQUEUE_FAILURE_COOLDOWN_SECONDS
            while loop.time() < fail_deadline and not stop_event.is_set():
                await asyncio.sleep(min(0.25, fail_deadline - loop.time()))
            continue

        if stop_event.is_set():
            break
        deadline = loop.time() + interval_seconds
        while loop.time() < deadline and not stop_event.is_set():
            await asyncio.sleep(min(0.25, deadline - loop.time()))


async def stop_refiner_failure_cleanup_enqueue_tasks(tasks: list[asyncio.Task[None]]) -> None:
    for t in tasks:
        if not t.done():
            t.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

