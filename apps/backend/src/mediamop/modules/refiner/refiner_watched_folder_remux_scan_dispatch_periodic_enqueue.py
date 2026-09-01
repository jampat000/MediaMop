"""Periodic asyncio enqueue for ``refiner.watched_folder.remux_scan_dispatch.v1`` (Refiner-only timer)."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.refiner_library_service import list_libraries, resolve_library
from mediamop.modules.refiner.refiner_operator_settings_service import (
    ensure_refiner_operator_settings_row,
    refiner_periodic_scope_in_schedule_window,
)
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


def refiner_library_periodic_scan_enabled(library: object) -> bool:
    """Whether periodic scanning is switched on for one library.

    Supersedes the per-scope operator toggle: a library carries its own switch, so a
    fourth library is scheduled independently of the seeded two (ADR-0014).
    """

    # ``schedule_enabled`` means "apply this processing window", not "stop
    # discovering files". Detection keeps the Files workbench truthful outside a run
    # window; leasing is where the schedule blocks expensive work (#337).
    return bool(getattr(library, "enabled", False))


def refiner_scope_periodic_scan_enabled(operator_row: object, *, media_scope: str) -> bool:
    """Whether periodic scanning is switched on for one scope.

    This is the *only* enable check the scheduler makes. It was inline in the tick
    closure, which meant the shipped behaviour could not be asserted directly and the
    coverage that existed tested an environment flag the scheduler never read (#329).
    """

    attr = "tv_schedule_enabled" if media_scope == "tv" else "movie_schedule_enabled"
    return bool(getattr(operator_row, attr))


def _watched_folder_scan_interval_seconds(library: object, *, media_scope: str) -> float:
    """The scan cadence configured on the library covering this scope.

    Read from the library rather than the singleton's per-scope column (#363). The scope
    argument stays because the scheduler ticks per scope and the caller resolves the
    library from it.
    """

    raw = getattr(library, "scan_interval_seconds", 300) if library is not None else 300
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
    next_run_by_library: dict[int, float] = {}
    while not stop_event.is_set():

        def _once(now_loop: float) -> float:
            with session_factory() as session:
                libraries = [
                    library for library in list_libraries(session) if refiner_library_periodic_scan_enabled(library)
                ]
                active_ids = {int(library.id) for library in libraries}
                for stale_id in set(next_run_by_library).difference(active_ids):
                    next_run_by_library.pop(stale_id, None)

                nearest = now_loop + 60.0
                for library in libraries:
                    library_id = int(library.id)
                    scope = "tv" if library.media_scope == "tv" else "movie"
                    interval = _watched_folder_scan_interval_seconds(library, media_scope=scope)
                    due = next_run_by_library.get(library_id, now_loop)
                    if now_loop < due:
                        nearest = min(nearest, due)
                        continue

                    missed = _missed_due_run_count(
                        now_loop=now_loop,
                        next_run_loop=due,
                        interval_seconds=interval,
                    )
                    if missed > 0:
                        logger.warning(
                            "Refiner watched-folder scheduler missed %s run(s) for library %s; enqueueing one catch-up scan",
                            missed,
                            library.name,
                        )

                    try:
                        inserted, skip = try_enqueue_periodic_watched_folder_remux_scan_dispatch(
                            session,
                            settings,
                            media_scope=scope,
                            library_id=library_id,
                        )
                        session.commit()
                    except Exception:
                        session.rollback()
                        logger.exception("Refiner watched-folder scheduler failed for library %s", library.name)
                        next_due = now_loop + REFINER_WATCHED_FOLDER_SCAN_DISPATCH_ENQUEUE_FAILURE_COOLDOWN_SECONDS
                    else:
                        # If an earlier scan is still queued, check again soon rather than
                        # losing a whole library interval. Every other outcome completed
                        # this tick and waits for the configured cadence.
                        active_skip = bool(skip and skip.startswith("active_scan_already_queued_"))
                        next_due = now_loop + (min(interval, 5.0) if not inserted and active_skip else interval)
                    next_run_by_library[library_id] = next_due
                    nearest = min(nearest, next_due)

                return max(0.25, min(60.0, nearest - now_loop))

        try:
            now_loop = loop.time()
            poll_seconds = await asyncio.to_thread(_once, now_loop)
            # ``stop_event.set`` may have been scheduled thread-safely by work that ran
            # inside ``_once``. A zero-delay yield can resume this task before that
            # callback under a busy suite, so allow one bounded handoff window before
            # deciding whether to start another library cycle.
            if not stop_event.is_set():
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop_event.wait(), timeout=0.01)
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
        deadline = loop.time() + max(0.25, float(poll_seconds))
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
