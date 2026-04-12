"""Periodic asyncio enqueue for ``refiner.supplied_payload_evaluation.v1`` (Refiner-only timer)."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.refiner_supplied_payload_evaluation_enqueue import (
    enqueue_refiner_supplied_payload_evaluation_job,
)

logger = logging.getLogger(__name__)

REFINER_SUPPLIED_PAYLOAD_EVALUATION_ENQUEUE_FAILURE_COOLDOWN_SECONDS = 2.0


def start_refiner_supplied_payload_evaluation_enqueue_tasks(
    session_factory: sessionmaker[Session],
    *,
    stop_event: asyncio.Event,
    settings: MediaMopSettings,
) -> list[asyncio.Task[None]]:
    """Background enqueue tick for the supplied-payload evaluation family only (no Fetcher coupling)."""

    if not settings.refiner_supplied_payload_evaluation_schedule_enabled:
        return []
    interval = float(settings.refiner_supplied_payload_evaluation_schedule_interval_seconds)
    if interval <= 0:
        return []
    task = asyncio.create_task(
        _run_periodic_supplied_payload_evaluation_enqueue(
            session_factory,
            stop_event=stop_event,
            interval_seconds=interval,
        ),
        name="refiner-supplied-payload-evaluation-enqueue",
    )
    return [task]


async def _run_periodic_supplied_payload_evaluation_enqueue(
    session_factory: sessionmaker[Session],
    *,
    stop_event: asyncio.Event,
    interval_seconds: float,
) -> None:
    loop = asyncio.get_running_loop()
    while not stop_event.is_set():

        def _once() -> None:
            with session_factory() as session:
                enqueue_refiner_supplied_payload_evaluation_job(session)
                session.commit()

        try:
            await asyncio.to_thread(_once)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Refiner supplied payload evaluation periodic enqueue failed")
            if stop_event.is_set():
                break
            fail_deadline = loop.time() + REFINER_SUPPLIED_PAYLOAD_EVALUATION_ENQUEUE_FAILURE_COOLDOWN_SECONDS
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


async def stop_refiner_supplied_payload_evaluation_enqueue_tasks(tasks: list[asyncio.Task[None]]) -> None:
    for t in tasks:
        if not t.done():
            t.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
