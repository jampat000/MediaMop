"""Decide, record and read a file's Refiner state.

The decision order matters and is not arbitrary. It runs cheapest-and-most-absolute
first, so the reason an operator is shown is the *first* thing standing in the way rather
than whichever check happened to run last:

1. **Disabled** — the library is switched off. Nothing else about the file is relevant.
2. **Out of schedule** — MediaMop is paused, or the library is on but not right now.
3. **On hold** — the file is still being written to, is too new, or cannot be opened.
4. **Blocked upstream** — a manager is still importing it.

Only a file that clears all four is unprocessed and eligible.

Within the hold step the order is also deliberate. Size settling is checked before the
access probe, because a file being written to is normally *also* locked: reporting "still
being written to" is the true cause, and reporting a permission error instead would send
an operator looking for a problem that does not exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.modules.refiner.refiner_file_state_model import RefinerFileRow, RefinerFileStatus
from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow


@dataclass(frozen=True, slots=True)
class FileStateVerdict:
    """A status and the sentence that explains it."""

    status: RefinerFileStatus
    reason: str
    blocked_by_connection: str | None = None
    #: When an on-hold file becomes eligible, when that is known. A hold waiting on a
    #: writer to stop has no release time, and saying otherwise would be a guess.
    hold_until: datetime | None = None

    @property
    def eligible(self) -> bool:
        return self.status is RefinerFileStatus.UNPROCESSED


def _scope_word(library: RefinerLibraryRow) -> str:
    return "TV episodes" if library.media_scope == "tv" else "Movies"


def decide_file_state(
    *,
    library: RefinerLibraryRow,
    in_schedule_window: bool,
    file_age_seconds: float | None,
    paused_reason: str | None = None,
    paused_until: datetime | None = None,
    window_reopens_at: datetime | None = None,
    size_is_settling: bool = False,
    settling_reason: str | None = None,
    settling_stable_at: datetime | None = None,
    access_problem: str | None = None,
    blocked_by_connection: str | None = None,
) -> FileStateVerdict:
    """Why this file is or is not being worked on, in the order the reasons apply."""

    if not library.enabled:
        return FileStateVerdict(
            RefinerFileStatus.DISABLED,
            f"The {library.name} library is switched off, so MediaMop is leaving its files alone.",
        )

    if paused_reason:
        # A paused instance is out of schedule in the only sense that matters to someone
        # looking at the screen: MediaMop is deliberately not working on this right now,
        # and this says why and until when.
        return FileStateVerdict(RefinerFileStatus.OUT_OF_SCHEDULE, paused_reason, hold_until=paused_until)

    if library.schedule_enabled and not in_schedule_window:
        return FileStateVerdict(
            RefinerFileStatus.OUT_OF_SCHEDULE,
            (
                f"The {library.name} library only runs inside its scheduled hours, and now is outside them. "
                "MediaMop will pick this up when the window opens."
            ),
            hold_until=window_reopens_at,
        )

    hold_seconds = max(0, int(library.min_file_age_seconds)) + max(0, int(library.hold_minutes)) * 60
    if size_is_settling:
        return FileStateVerdict(
            RefinerFileStatus.ON_HOLD,
            settling_reason
            or "This file is still being written to, so MediaMop is waiting for it to finish before touching it.",
            hold_until=settling_stable_at,
        )
    if hold_seconds and file_age_seconds is not None and file_age_seconds < hold_seconds:
        remaining = int(hold_seconds - file_age_seconds)
        return FileStateVerdict(
            RefinerFileStatus.ON_HOLD,
            (
                f"This file changed too recently. MediaMop waits {hold_seconds}s after the last change before "
                f"processing, so it has about {remaining}s to go."
            ),
            hold_until=datetime.now(UTC) + timedelta(seconds=remaining),
        )
    if access_problem:
        # No release time: this clears when whatever holds the file lets go, and every
        # scan re-checks it. A countdown here would be a number MediaMop invented.
        return FileStateVerdict(RefinerFileStatus.ON_HOLD, access_problem)

    if blocked_by_connection:
        return FileStateVerdict(
            RefinerFileStatus.BLOCKED_UPSTREAM,
            f"{blocked_by_connection} is still importing this file, so MediaMop left it alone for now.",
            blocked_by_connection=blocked_by_connection,
        )

    return FileStateVerdict(
        RefinerFileStatus.UNPROCESSED,
        f"Ready for Refiner to process as part of {_scope_word(library)}.",
    )


def existing_file_row(session: Session, *, library_id: int, relative_path: str) -> RefinerFileRow | None:
    """The row a previous scan left, or None. Settling compares against this."""

    return session.scalars(
        select(RefinerFileRow)
        .where(RefinerFileRow.library_id == library_id)
        .where(RefinerFileRow.relative_path == relative_path)
    ).first()


def record_file_state(
    session: Session,
    *,
    library: RefinerLibraryRow,
    relative_path: str,
    verdict: FileStateVerdict,
    size_bytes: int | None = None,
    size_changed_at: datetime | None = None,
    seen_at: datetime | None = None,
    is_attempt: bool = False,
) -> RefinerFileRow:
    """Upsert one file's state. Safe to call on every scan."""

    now = seen_at or datetime.now(UTC)
    row = session.scalars(
        select(RefinerFileRow)
        .where(RefinerFileRow.library_id == library.id)
        .where(RefinerFileRow.relative_path == relative_path)
    ).first()
    if row is None:
        row = RefinerFileRow(library_id=library.id, relative_path=relative_path)
        session.add(row)
    row.status = verdict.status.value
    row.status_reason = verdict.reason
    row.blocked_by_connection = verdict.blocked_by_connection
    row.hold_until = verdict.hold_until
    # ``None`` means "not supplied", which is distinct from a genuine zero. Treating them
    # alike would let an empty placeholder look like it never changed, and would blank the
    # size for callers that only update a status.
    if size_bytes is not None:
        row.size_bytes = int(size_bytes)
    if size_changed_at is not None:
        row.size_changed_at = size_changed_at
    row.last_seen_at = now
    if is_attempt:
        row.last_attempt_at = now
    session.flush()
    return row


def mark_file_status(
    session: Session,
    *,
    library_id: int,
    relative_path: str,
    status: RefinerFileStatus,
    reason: str,
) -> RefinerFileRow | None:
    """Move a file MediaMop has already seen into a new state (processing, processed, failed)."""

    row = session.scalars(
        select(RefinerFileRow)
        .where(RefinerFileRow.library_id == library_id)
        .where(RefinerFileRow.relative_path == relative_path)
    ).first()
    if row is None:
        return None
    row.status = status.value
    row.status_reason = reason
    if status in (RefinerFileStatus.PROCESSING, RefinerFileStatus.PROCESSED, RefinerFileStatus.PROCESSING_FAILED):
        row.last_attempt_at = datetime.now(UTC)
    if status is not RefinerFileStatus.BLOCKED_UPSTREAM:
        row.blocked_by_connection = None
    if status is not RefinerFileStatus.ON_HOLD:
        row.hold_until = None
    session.flush()
    return row


def status_counts(session: Session, *, library_id: int | None = None) -> dict[str, int]:
    """Counts per status, for the buckets across the top of the Files screen."""

    counts = dict.fromkeys((s.value for s in RefinerFileStatus), 0)
    stmt = select(RefinerFileRow.status)
    if library_id is not None:
        stmt = stmt.where(RefinerFileRow.library_id == library_id)
    for value in session.scalars(stmt):
        if value in counts:
            counts[value] += 1
    return counts


def list_files(
    session: Session,
    *,
    library_id: int | None = None,
    status: str | None = None,
    path_contains: str | None = None,
    since: datetime | None = None,
    limit: int = 200,
) -> list[RefinerFileRow]:
    stmt = select(RefinerFileRow)
    if library_id is not None:
        stmt = stmt.where(RefinerFileRow.library_id == library_id)
    if status:
        stmt = stmt.where(RefinerFileRow.status == status)
    if path_contains:
        stmt = stmt.where(RefinerFileRow.relative_path.ilike(f"%{path_contains}%"))
    if since is not None:
        stmt = stmt.where(RefinerFileRow.last_seen_at >= since)
    stmt = stmt.order_by(RefinerFileRow.last_seen_at.desc(), RefinerFileRow.id.desc()).limit(max(1, min(limit, 1000)))
    return list(session.scalars(stmt))


def forget_file(session: Session, row: RefinerFileRow) -> None:
    """Remove a file from the list. The file on disk is untouched."""

    session.delete(row)
    session.flush()


def record_measured_video_dimensions(
    session: Session,
    *,
    relative_path: str,
    video_width: int | None,
    video_height: int | None,
) -> None:
    """Remember the size a pass measured, for weighting the next enqueue.

    Matched on path alone rather than on ``(library_id, path)``: the pass knows the file
    it processed but not which library row the scan attributed it to, and a resolution is
    a property of the file rather than of the library looking at it. Writing to every
    matching row is correct for the same reason.
    """

    rows = session.scalars(select(RefinerFileRow).where(RefinerFileRow.relative_path == relative_path)).all()
    for row in rows:
        if video_width is not None:
            row.video_width = int(video_width)
        if video_height is not None:
            row.video_height = int(video_height)
    if rows:
        session.flush()
