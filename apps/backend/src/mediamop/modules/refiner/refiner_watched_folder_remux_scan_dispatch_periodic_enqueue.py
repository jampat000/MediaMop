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

        def _once(now_loop: float) -> tuple[float, float, float]:
            with session_factory() as session:
                row = ensure_refiner_operator_settings_row(session)
                path_row = ensure_refiner_path_settings_row(session)
                next_movie = next_run_movie
                next_tv = next_run_tv
                if (
                    bool(row.movie_schedule_enabled)
                    and now_loop >= next_run_movie
                    and refiner_periodic_scope_in_schedule_window(session, row, media_scope="movie")
                ):
                    try_enqueue_periodic_watched_folder_remux_scan_dispatch(session, settings, media_scope="movie")
                    next_movie = now_loop + _watched_folder_scan_interval_seconds(path_row, media_scope="movie")
                if (
                    bool(row.tv_schedule_enabled)
                    and now_loop >= next_run_tv
                    and refiner_periodic_scope_in_schedule_window(session, row, media_scope="tv")
                ):
                    try_enqueue_periodic_watched_folder_remux_scan_dispatch(session, settings, media_scope="tv")
                    next_tv = now_loop + _watched_folder_scan_interval_seconds(path_row, media_scope="tv")
                session.commit()
                poll_movie = _watched_folder_scan_interval_seconds(path_row, media_scope="movie")
                poll_tv = _watched_folder_scan_interval_seconds(path_row, media_scope="tv")
                poll_s = min(poll_movie, poll_tv)
                return next_movie, next_tv, poll_s

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
        deadline = loop.time() + poll_seconds
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
