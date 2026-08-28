"""Filesystem events as the trigger; the periodic scan as the backstop.

Refiner found work by walking the whole watched tree on a timer. That means latency of up
to a full interval between a file landing and Refiner noticing, and a full-tree stat storm
every tick whether or not anything changed.

This watches instead. What it deliberately does **not** do is decide anything about a
file: an event debounces into exactly the same
``refiner.watched_folder.remux_scan_dispatch.v1`` job the timer enqueues, carrying
``scan_trigger="filesystem_event"``. Extension checks, exclusions, size limits, the hold
timer and size settling all stay in the one handler that already owns them. A second
admission path that agreed with the first today would disagree with it within a release.

The periodic scan is unchanged and still runs. Docker bind mounts, SMB and NFS frequently
deliver no inotify events at all, so the fallback is not a nicety — it is the primary
compatibility story, and a watcher that cannot start degrades to it loudly rather than
leaving an operator with a Refiner that has quietly stopped finding work.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow
from mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_enqueue import (
    enqueue_watched_folder_remux_scan_dispatch_job,
    refiner_watched_folder_remux_scan_dispatch_queue_has_active_scan,
)
from mediamop.modules.refiner.refiner_watcher_state import (
    WatcherReport,
    WatcherStatus,
    clear_watcher_state,
    record_watcher_state,
)

logger = logging.getLogger(__name__)

#: How long the tree must be quiet before an event turns into a scan. A copy lands as a
#: burst of write events, and one candidate per burst is the point.
DEFAULT_DEBOUNCE_SECONDS = 3.0
#: How often the debounce timer is examined. Small enough to keep the promise of "within
#: seconds", large enough not to spin.
_TICK_SECONDS = 0.5


class PendingChanges:
    """Thread-safe handoff from watchdog's threads to the asyncio task.

    watchdog calls handlers on its own threads, so the event side and the drain side
    never touch the same state without this lock.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._libraries: dict[int, float] = {}

    def note(self, library_id: int, at_monotonic: float) -> None:
        with self._lock:
            self._libraries[library_id] = at_monotonic

    def drain_quiet(self, *, now_monotonic: float, debounce_seconds: float) -> list[int]:
        """Library ids whose last event is older than the debounce window."""

        with self._lock:
            ready = [lib for lib, last in self._libraries.items() if now_monotonic - last >= debounce_seconds]
            for lib in ready:
                self._libraries.pop(lib, None)
            return sorted(ready)

    def pending_count(self) -> int:
        with self._lock:
            return len(self._libraries)


def _watchdog_modules() -> tuple[Any, Any] | None:
    """``(Observer, FileSystemEventHandler)``, or None when watchdog is unavailable.

    Imported here rather than at module scope so a missing or broken watchdog is a
    fallback to polling, not an import error that takes the whole application down.
    """

    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except Exception:  # pragma: no cover - exercised via the unavailable-watcher test
        return None
    return Observer, FileSystemEventHandler


def libraries_to_watch(session: Session) -> list[RefinerLibraryRow]:
    """Enabled libraries with a watched folder and events switched on."""

    rows = session.scalars(
        select(RefinerLibraryRow).where(RefinerLibraryRow.enabled.is_(True)).order_by(RefinerLibraryRow.id)
    ).all()
    return [row for row in rows if (row.watched_folder or "").strip() and row.file_system_events_enabled]


def disabled_watch_reports(session: Session) -> list[WatcherReport]:
    """Reports for libraries that deliberately are not watched, so the screen can say so."""

    rows = session.scalars(
        select(RefinerLibraryRow).where(RefinerLibraryRow.enabled.is_(True)).order_by(RefinerLibraryRow.id)
    ).all()
    return [
        WatcherReport(
            library_id=row.id,
            library_name=row.name,
            watched_folder=row.watched_folder or "",
            status=WatcherStatus.DISABLED,
            detail=(
                f"Filesystem events are switched off for {row.name}, so MediaMop finds new files on the scan interval."
            ),
        )
        for row in rows
        if (row.watched_folder or "").strip() and not row.file_system_events_enabled
    ]


def _debounce_seconds(settings: MediaMopSettings) -> float:
    raw = getattr(settings, "refiner_watcher_debounce_seconds", DEFAULT_DEBOUNCE_SECONDS)
    return max(0.25, min(float(raw), 300.0))


def enqueue_scan_for_library(
    session: Session,
    settings: MediaMopSettings,
    *,
    library: RefinerLibraryRow,
) -> tuple[bool, str | None]:
    """Turn a settled burst of events into one scan job.

    Identical to what the timer enqueues apart from ``scan_trigger``, which is the whole
    design: there is one admission implementation and this is not a second one.
    """

    scope = "tv" if library.media_scope == "tv" else "movie"
    if refiner_watched_folder_remux_scan_dispatch_queue_has_active_scan(session, media_scope=scope):
        # A queued scan will already look at this file. Adding another would mean two
        # walks of the same tree for one arrival.
        return False, "active_scan_already_queued"
    if (
        not (library.output_folder or "").strip()
        and settings.refiner_watched_folder_remux_scan_dispatch_periodic_enqueue_remux_jobs
    ):
        return False, "missing_output_for_live_remux"
    enqueue_watched_folder_remux_scan_dispatch_job(
        session,
        enqueue_remux_jobs=settings.refiner_watched_folder_remux_scan_dispatch_periodic_enqueue_remux_jobs,
        scan_trigger="filesystem_event",
        media_scope=scope,
        library_id=library.id,
    )
    return True, None


def _start_observer(
    observer_cls: Any,
    handler_cls: Any,
    *,
    libraries: list[RefinerLibraryRow],
    pending: PendingChanges,
) -> tuple[Any, list[WatcherReport]]:
    """One observer, one scheduled watch per library. Failures become reports, not raises."""

    class _Handler(handler_cls):
        def __init__(self, library_id: int) -> None:
            super().__init__()
            self._library_id = library_id

        def on_any_event(self, event: Any) -> None:
            # Deletions are not work appearing, and a directory event is always
            # accompanied by the file event that matters.
            if getattr(event, "is_directory", False):
                return
            if getattr(event, "event_type", "") == "deleted":
                return
            import time as _time

            pending.note(self._library_id, _time.monotonic())

    observer = observer_cls()
    reports: list[WatcherReport] = []
    scheduled = 0
    for library in libraries:
        folder = Path((library.watched_folder or "").strip())
        try:
            if not folder.is_dir():
                raise OSError(f"{folder} is not a folder MediaMop can see")
            observer.schedule(_Handler(library.id), str(folder), recursive=True)
        except Exception as exc:
            reports.append(
                WatcherReport(
                    library_id=library.id,
                    library_name=library.name,
                    watched_folder=str(folder),
                    status=WatcherStatus.POLLING_FALLBACK,
                    detail=(
                        f"MediaMop could not watch {folder} for changes, so it is finding new files on the "
                        f"scan interval instead. This is normal for network shares and some container mounts. "
                        f"The system reported: {exc}."
                    ),
                )
            )
            continue
        scheduled += 1
        reports.append(
            WatcherReport(
                library_id=library.id,
                library_name=library.name,
                watched_folder=str(folder),
                status=WatcherStatus.WATCHING,
                detail=f"Watching {folder} for changes. The periodic scan still runs as a backstop.",
            )
        )

    if scheduled == 0:
        return None, reports
    observer.start()
    return observer, reports


def start_refiner_watched_folder_watcher_tasks(
    session_factory: sessionmaker[Session],
    *,
    stop_event: asyncio.Event,
    settings: MediaMopSettings,
) -> list[asyncio.Task[None]]:
    """Background filesystem watcher for Refiner's watched folders."""

    task = asyncio.create_task(
        _run_refiner_watched_folder_watcher(session_factory, stop_event=stop_event, settings=settings),
        name="refiner-watched-folder-watcher",
    )
    return [task]


async def _run_refiner_watched_folder_watcher(
    session_factory: sessionmaker[Session],
    *,
    stop_event: asyncio.Event,
    settings: MediaMopSettings,
) -> None:
    pending = PendingChanges()
    observer: Any = None
    watched: dict[int, RefinerLibraryRow] = {}

    try:
        with session_factory() as session:
            libraries = libraries_to_watch(session)
            watched = {row.id: row for row in libraries}
            for report in disabled_watch_reports(session):
                record_watcher_state(report)

        modules = _watchdog_modules()
        if modules is None:
            # One line, once. A per-tick warning about a machine that will never deliver
            # events is noise that buries the next real problem.
            logger.warning(
                "Refiner is finding new files on the scan interval because the filesystem watcher is "
                "unavailable in this environment. Nothing is missed; new files are picked up more slowly."
            )
            for row in libraries:
                record_watcher_state(
                    WatcherReport(
                        library_id=row.id,
                        library_name=row.name,
                        watched_folder=row.watched_folder or "",
                        status=WatcherStatus.POLLING_FALLBACK,
                        detail=(
                            "The filesystem watcher is not available in this environment, so MediaMop finds "
                            "new files on the scan interval."
                        ),
                    )
                )
            await stop_event.wait()
            return

        observer_cls, handler_cls = modules
        observer, reports = _start_observer(observer_cls, handler_cls, libraries=libraries, pending=pending)
        for report in reports:
            record_watcher_state(report)
            if report.degraded:
                logger.warning("Refiner filesystem watcher: %s", report.detail)

        if observer is None:
            await stop_event.wait()
            return

        debounce = _debounce_seconds(settings)
        loop = asyncio.get_running_loop()
        while not stop_event.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop_event.wait(), timeout=_TICK_SECONDS)
            if stop_event.is_set():
                break
            ready = pending.drain_quiet(now_monotonic=loop.time(), debounce_seconds=debounce)
            if not ready:
                continue
            try:
                with session_factory() as session, session.begin():
                    for library_id in ready:
                        library = watched.get(library_id)
                        if library is None:
                            continue
                        fresh = session.get(RefinerLibraryRow, library_id)
                        if fresh is None or not fresh.enabled:
                            continue
                        inserted, skip = enqueue_scan_for_library(session, settings, library=fresh)
                        if inserted:
                            logger.info("Refiner queued a scan of %s because its watched folder changed.", fresh.name)
                        else:
                            logger.debug("Refiner did not queue a watcher scan for %s: %s", fresh.name, skip)
            except Exception:
                # A failed enqueue must not kill the watcher: the periodic scan is still
                # running, and the next event gets another attempt.
                logger.exception("Refiner filesystem watcher could not queue a scan.")
    finally:
        if observer is not None:
            with contextlib.suppress(Exception):
                observer.stop()
                observer.join(timeout=5)
        clear_watcher_state()


async def stop_refiner_watched_folder_watcher_tasks(tasks: list[asyncio.Task[None]]) -> None:
    for task in tasks:
        task.cancel()
    for task in tasks:
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
