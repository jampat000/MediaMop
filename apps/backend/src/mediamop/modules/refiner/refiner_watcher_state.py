"""What the filesystem watcher is actually doing, for anything that needs to report it.

Kept apart from the watcher itself, and deliberately free of any ``watchdog`` import, so
readiness can ask "is the watcher working?" on a machine where the library is missing or
the platform backend refused to start. A readiness probe that cannot run without the
thing it is probing is not a probe.

Process-local on purpose. This is the state of *this* process's observers; persisting it
would make a stale row from a previous run look like the current answer.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import StrEnum


class WatcherStatus(StrEnum):
    """How a library's watched folder is being monitored."""

    #: Filesystem events are arriving. The periodic scan still runs as the backstop.
    WATCHING = "watching"
    #: The watcher could not start or has stopped. The periodic scan is the only
    #: mechanism finding work, which still works — it is just slower.
    POLLING_FALLBACK = "polling_fallback"
    #: Switched off for this library by an operator.
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class WatcherReport:
    """One library's watcher state and the sentence explaining it."""

    library_id: int
    library_name: str
    watched_folder: str
    status: WatcherStatus
    detail: str

    @property
    def degraded(self) -> bool:
        """True only for a watcher that was meant to run and is not.

        A library an operator switched off is not degraded, and reporting it as such
        would train people to ignore the signal.
        """

        return self.status is WatcherStatus.POLLING_FALLBACK


_lock = threading.Lock()
_reports: dict[int, WatcherReport] = {}


def record_watcher_state(report: WatcherReport) -> None:
    with _lock:
        _reports[report.library_id] = report


def forget_watcher_state(library_id: int) -> None:
    with _lock:
        _reports.pop(library_id, None)


def clear_watcher_state() -> None:
    """Drop everything. Called on shutdown, and by tests between cases."""

    with _lock:
        _reports.clear()


def watcher_reports() -> tuple[WatcherReport, ...]:
    with _lock:
        return tuple(sorted(_reports.values(), key=lambda r: r.library_id))


def watcher_summary() -> tuple[bool, str]:
    """``(ok, sentence)`` for readiness.

    Falling back to polling is *not* a failure — MediaMop still finds every file, just on
    the scan interval rather than within seconds. So this reports "ok" with a sentence
    naming the affected libraries rather than failing readiness and taking an instance
    out of a load balancer over a slower path to the same result.
    """

    reports = watcher_reports()
    if not reports:
        return True, "No libraries are being watched for filesystem events."
    degraded = [r for r in reports if r.degraded]
    watching = [r for r in reports if r.status is WatcherStatus.WATCHING]
    if not degraded:
        return True, f"Watching {len(watching)} folder(s) for changes; the periodic scan is the backstop."
    names = ", ".join(r.library_name for r in degraded)
    return (
        True,
        (
            f"Falling back to the periodic scan for {names}. MediaMop still finds every file, "
            "but new ones are picked up on the scan interval instead of within seconds."
        ),
    )
