"""Periodic asyncio enqueue for ``refiner.work_temp_stale_sweep.v1`` (Refiner-only; Movies vs TV separate)."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Literal

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.refiner_operator_settings_service import ensure_refiner_operator_settings_row
from mediamop.modules.refiner.refiner_work_temp_stale_sweep_enqueue import (
    enqueue_refiner_work_temp_stale_sweep_job,
)

logger = logging.getLogger(__name__)

REFINER_WORK_TEMP_STALE_SWEEP_ENQUEUE_FAILURE_COOLDOWN_SECONDS = 2.0


_ENV_KILL_SWITCH = {"work_temp_stale_sweep_enabled": "refiner_work_temp_stale_sweep_movie_schedule_enabled"}
_ENV_KILL_SWITCH_VARIABLE = {
    "work_temp_stale_sweep_enabled": "MEDIAMOP_REFINER_WORK_TEMP_STALE_SWEEP_MOVIE_SCHEDULE_ENABLED"
}


def _sweep_enabled(session_factory: sessionmaker[Session], settings: MediaMopSettings, *, attribute: str) -> bool:
    """Whether this sweep runs, read from the database rather than the environment.

    The environment variable is kept as a **kill switch only**: an explicit 0 still turns
    the sweep off, so an operator who deliberately disabled it does not find it running
    again after an upgrade. It can no longer be the thing that *enables* a family nobody
    can see, which was the bug (#339).
    """

    variable = _ENV_KILL_SWITCH_VARIABLE.get(attribute)
    if variable and variable in os.environ and not getattr(settings, _ENV_KILL_SWITCH[attribute], True):
        return False
    try:
        with session_factory() as session:
            row = ensure_refiner_operator_settings_row(session)
            enabled = bool(getattr(row, attribute))
            session.commit()
            return enabled
    except Exception:
        logger.exception("Refiner could not read whether the %s sweep is enabled; leaving it off.", attribute)
        return False


def start_refiner_work_temp_stale_sweep_enqueue_tasks(
    session_factory: sessionmaker[Session],
    *,
    stop_event: asyncio.Event,
    settings: MediaMopSettings,
) -> list[asyncio.Task[None]]:
    """Background enqueue ticks: **independent** Movies and TV timers when each scope is enabled."""

    tasks: list[asyncio.Task[None]] = []
    enabled = _sweep_enabled(session_factory, settings, attribute="work_temp_stale_sweep_enabled")
    if enabled:
        iv = float(settings.refiner_work_temp_stale_sweep_movie_schedule_interval_seconds)
        if iv > 0:
            tasks.append(
                asyncio.create_task(
                    _run_periodic_scope_enqueue(
                        session_factory,
                        stop_event=stop_event,
                        interval_seconds=iv,
                        media_scope="movie",
                    ),
                    name="refiner-work-temp-stale-sweep-enqueue-movie",
                ),
            )
    if enabled:
        iv = float(settings.refiner_work_temp_stale_sweep_tv_schedule_interval_seconds)
        if iv > 0:
            tasks.append(
                asyncio.create_task(
                    _run_periodic_scope_enqueue(
                        session_factory,
                        stop_event=stop_event,
                        interval_seconds=iv,
                        media_scope="tv",
                    ),
                    name="refiner-work-temp-stale-sweep-enqueue-tv",
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
                enqueue_refiner_work_temp_stale_sweep_job(session, media_scope=media_scope)
                session.commit()

        try:
            await asyncio.to_thread(_once)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Refiner work temp stale sweep periodic enqueue failed (media_scope=%s)",
                media_scope,
            )
            if stop_event.is_set():
                break
            fail_deadline = loop.time() + REFINER_WORK_TEMP_STALE_SWEEP_ENQUEUE_FAILURE_COOLDOWN_SECONDS
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


async def stop_refiner_work_temp_stale_sweep_enqueue_tasks(tasks: list[asyncio.Task[None]]) -> None:
    for t in tasks:
        if not t.done():
            t.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
