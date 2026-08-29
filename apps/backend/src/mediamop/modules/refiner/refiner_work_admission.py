"""Whether Refiner may take on new work right now, and why not.

The schedule used to gate **enqueue** only. Once a job was queued it ran to completion
regardless, so a 4K remux started two minutes before the window closed ran into the
morning — which is exactly the outcome the window existed to prevent. And there was no
pause of any kind, on a tool whose whole job is sustained disk and CPU load on a machine
someone is also using.

So admission is evaluated at **lease** time, not only at enqueue time.

**In-flight policy: a job already running finishes.** Killing a transcode partway through
wastes the work done and leaves a partial file to reason about, and the alternative —
checkpoint and requeue — is a much larger promise than a schedule needs to make. The
window therefore means "start nothing new", and the UI says exactly that rather than
implying work stops dead at the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow
from mediamop.modules.refiner.refiner_schedule_grid import grid_allows, next_open_slot
from mediamop.platform.media_managers.schedule_wall_clock import schedule_time_window_active
from mediamop.platform.suite_settings.model import SuiteSettingsRow

#: Job kinds that are detection rather than processing. These keep running through a
#: pause when "scan while paused" is on, because noticing a file costs nothing and
#: refusing to notice it only hides work that is arriving anyway.
DETECTION_JOB_KIND_PREFIXES: tuple[str, ...] = (
    "refiner.watched_folder.remux_scan_dispatch",
    "refiner.supplied_payload_evaluation",
)


def is_detection_job_kind(job_kind: str) -> bool:
    return any(job_kind.startswith(prefix) for prefix in DETECTION_JOB_KIND_PREFIXES)


@dataclass(frozen=True, slots=True)
class PauseState:
    """The suite-wide pause, already resolved against the clock."""

    paused: bool
    paused_until: datetime | None
    scan_while_paused: bool
    #: True when a ``paused_until`` in the past means this pause has lapsed. The stored
    #: flag is left alone; expiry is evaluated on read so a stopped process cannot leave
    #: an instance paused forever.
    expired: bool = False

    @property
    def reason(self) -> str:
        if not self.paused:
            return ""
        if self.paused_until is not None:
            return (
                "Processing is paused. MediaMop will start work again automatically at "
                f"{self.paused_until.astimezone(UTC).strftime('%Y-%m-%d %H:%M')} UTC."
            )
        return "Processing is paused. MediaMop will start work again when you resume it."


def resolve_pause_state(row: SuiteSettingsRow, *, now: datetime | None = None) -> PauseState:
    """Read the pause, honouring its expiry.

    Expiry is applied here rather than by a background task, so a pause set before a
    restart still lapses on time.
    """

    moment = now or datetime.now(UTC)
    until = row.processing_paused_until
    if until is not None and until.tzinfo is None:
        until = until.replace(tzinfo=UTC)
    if not row.processing_paused:
        return PauseState(paused=False, paused_until=None, scan_while_paused=bool(row.scan_while_paused))
    if until is not None and moment >= until:
        return PauseState(
            paused=False,
            paused_until=until,
            scan_while_paused=bool(row.scan_while_paused),
            expired=True,
        )
    return PauseState(paused=True, paused_until=until, scan_while_paused=bool(row.scan_while_paused))


def library_window_open(
    library: RefinerLibraryRow,
    *,
    timezone_name: str,
    now: datetime | None = None,
) -> bool:
    """Whether this library's schedule allows work at this moment.

    The grid wins when one is drawn. Falling back to the day/start/end trio keeps every
    library that has not been given a grid behaving exactly as it did.
    """

    if not library.schedule_enabled:
        return True
    moment = now or datetime.now(UTC)
    grid = (library.schedule_grid or "").strip()
    if grid:
        return grid_allows(grid, timezone_name=timezone_name, now=moment)
    if not library.schedule_hours_limited:
        return True
    return schedule_time_window_active(
        schedule_enabled=True,
        schedule_days=(library.schedule_days or "").strip(),
        schedule_start=(library.schedule_start or "00:00").strip(),
        schedule_end=(library.schedule_end or "23:59").strip(),
        timezone_name=timezone_name,
        now=moment,
    )


def library_window_reopens_at(
    library: RefinerLibraryRow,
    *,
    timezone_name: str,
    now: datetime | None = None,
) -> datetime | None:
    """When a closed window next opens, when that is knowable from a grid."""

    grid = (library.schedule_grid or "").strip()
    if not grid:
        return None
    return next_open_slot(grid, timezone_name=timezone_name, now=now or datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class WorkAdmission:
    """What a worker is allowed to pick up on this pass."""

    pause: PauseState
    #: Libraries whose window is shut. A job naming one of these is not leased.
    blocked_library_ids: frozenset[int] = field(default_factory=frozenset)
    timezone_name: str = "UTC"

    @property
    def blocks_processing(self) -> bool:
        return self.pause.paused

    @property
    def blocks_detection(self) -> bool:
        return self.pause.paused and not self.pause.scan_while_paused

    def allows_job_kind(self, job_kind: str) -> bool:
        if not self.pause.paused:
            return True
        return is_detection_job_kind(job_kind) and self.pause.scan_while_paused


def evaluate_work_admission(session: Session, *, now: datetime | None = None) -> WorkAdmission:
    """Read the pause and every library window once, for one pass of the worker loop."""

    moment = now or datetime.now(UTC)
    suite = session.scalars(select(SuiteSettingsRow).where(SuiteSettingsRow.id == 1)).one_or_none()
    if suite is None:
        return WorkAdmission(pause=PauseState(paused=False, paused_until=None, scan_while_paused=True))
    tz_name = (suite.app_timezone or "UTC").strip() or "UTC"
    pause = resolve_pause_state(suite, now=moment)

    blocked: set[int] = set()
    for library in session.scalars(select(RefinerLibraryRow).order_by(RefinerLibraryRow.id)):
        if not library.enabled or not library_window_open(library, timezone_name=tz_name, now=moment):
            blocked.add(int(library.id))
    return WorkAdmission(pause=pause, blocked_library_ids=frozenset(blocked), timezone_name=tz_name)
