"""Periodic asyncio enqueue for ``refiner.watched_folder.remux_scan_dispatch.v1`` (Refiner-only timer)."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.refiner_operator_settings_service import (
    ensure_refiner_operator_settings_row,
    refiner_periodic_scope_in_schedule_window,
)
from mediamop.modules.refiner.refiner_path_settings_service import ensure_refiner_path_settings_row
from mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_enqueue import (
    try_enqueue_periodic_watched_folder_remux_scan_dispatch,
)

logger = logging.getLogger(__name__)

REFINER_WATCHED_FOLDER_SCAN_DISPATCH_ENQUEUE_FAILURE_COOLDOWN_SECONDS = 2.0


def _missed_due_run_count(*, now_loop: float, next_run_loop: float, interval_seconds: float) -> int:
    """Return how many configured intervals elapsed after the next due time."""

    interval = max(1.0, float(interval_seconds))
    if now_loop <= next_run_loop:
        return 0
    return int((now_loop - next_run_loop) // interval)


def _next_scheduler_sleep_seconds(
    *,
    now_loop: float,
    next_run_movie: float,
    next_run_tv: float,
    poll_seconds: float,
) -> float:
    """Sleep until the nearest due scope, capped by the configured polling cadence."""

    next_due = min(float(next_run_movie), float(next_run_tv))
    until_due = max(0.25, next_due - now_loop)
    return max(0.25, min(float(poll_seconds), until_due))


def _watched_folder_scan_interval_seconds(path_row: object, *, media_scope: str) -> float:
    """Actual watched-folder scan cadence configured on the Refiner Libraries tab."""

    if media_scope == "tv":
        raw = getattr(path_row, "tv_watched_folder_check_interval_seconds", 300)
    else:
        raw = getattr(path_row, "movie_watched_folder_check_interval_seconds", 300)
    return max(10.0, min(float(raw), float(7 * 24 * 3600)))


def start_refiner_watched_folder_remux_scan_dispatch_enqueue_tasks(
    session_factory: sessionmaker[Session],
    *,
    stop_event: asyncio.Event,
    settings: MediaMopSettings,
) -> list[asyncio.Task[None]]:
    """Background enqueue tick for the watched-folder remux scan dispatch family only."""
    task = asyncio.create_task(
        _run_periodic_watched_folder_scan_dispatch_enqueue(
            session_factory,
            stop_event=stop_event,
            settings=settings,
        ),
        name="refiner-watched-folder-remux-scan-dispatch-enqueue",
    )
    return [task]


async def _run_periodic_watched_folder_scan_dispatch_enqueue(
    session_factory: sessionmaker[Session],
    *,
    stop_event: asyncio.Event,
    settings: MediaMopSettings,
) -> None:
    loop = asyncio.get_running_loop()
    next_run_movie = loop.time()
    next_run_tv = loop.time()
    while not stop_event.is_set():

        def _scope_once(media_scope: str, *, now_loop: float, next_run_loop: float) -> tuple[float, float]:
            with session_factory() as session:
                row = ensure_refiner_operator_settings_row(session)
                path_row = ensure_refiner_path_settings_row(session)
                interval = _watched_folder_scan_interval_seconds(path_row, media_scope=media_scope)
                enabled_attr = "tv_schedule_enabled" if media_scope == "tv" else "movie_schedule_enabled"
                if not bool(getattr(row, enabled_attr)):
                    return next_run_loop, interval
                if now_loop < next_run_loop:
                    return next_run_loop, interval
                if not refiner_periodic_scope_in_schedule_window(session, row, media_scope=media_scope):
                    return now_loop + min(interval, 60.0), interval

                missed = _missed_due_run_count(
                    now_loop=now_loop,
                    next_run_loop=next_run_loop,
                    interval_seconds=interval,
                )
                if missed > 0:
                    logger.warning(
                        "Refiner watched-folder scheduler missed %s %s run(s); enqueueing one catch-up scan",
                        missed,
                        media_scope,
                    )

                try:
                    try_enqueue_periodic_watched_folder_remux_scan_dispatch(session, settings, media_scope=media_scope)
                except Exception:
                    session.rollback()
                    logger.exception("Refiner watched-folder scheduler failed for %s scope", media_scope)
                    return (
                        now_loop + REFINER_WATCHED_FOLDER_SCAN_DISPATCH_ENQUEUE_FAILURE_COOLDOWN_SECONDS,
                        interval,
                    )
                session.commit()
                return now_loop + interval, interval

        def _once(now_loop: float) -> tuple[float, float, float]:
            next_movie, poll_movie = _scope_once("movie", now_loop=now_loop, next_run_loop=next_run_movie)
            next_tv, poll_tv = _scope_once("tv", now_loop=now_loop, next_run_loop=next_run_tv)
            return next_movie, next_tv, min(poll_movie, poll_tv)

        try:
            now_loop = loop.time()
            next_vals = await asyncio.to_thread(_once, now_loop)
            poll_seconds = 1.0
            if next_vals is not None:
                next_run_movie, next_run_tv, poll_seconds = next_vals
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Refiner watched-folder remux scan dispatch periodic enqueue failed")
            if stop_event.is_set():
                break
            fail_deadline = loop.time() + REFINER_WATCHED_FOLDER_SCAN_DISPATCH_ENQUEUE_FAILURE_COOLDOWN_SECONDS
            while loop.time() < fail_deadline and not stop_event.is_set():
                remaining = fail_deadline - loop.time()
                if remaining <= 0:
                    break
                await asyncio.sleep(min(0.25, remaining))
            continue

        if stop_event.is_set():
            break
        deadline = loop.time() + _next_scheduler_sleep_seconds(
            now_loop=loop.time(),
            next_run_movie=next_run_movie,
            next_run_tv=next_run_tv,
            poll_seconds=poll_seconds,
        )
        while loop.time() < deadline and not stop_event.is_set():
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            await asyncio.sleep(min(0.25, remaining))


async def stop_refiner_watched_folder_remux_scan_dispatch_enqueue_tasks(tasks: list[asyncio.Task[None]]) -> None:
    for t in tasks:
        if not t.done():
            t.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
