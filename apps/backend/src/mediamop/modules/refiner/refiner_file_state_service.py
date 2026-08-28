"""Decide, record and read a file's Refiner state.

The decision order matters and is not arbitrary. It runs cheapest-and-most-absolute
first, so the reason an operator is shown is the *first* thing standing in the way rather
than whichever check happened to run last:

1. **Disabled** — the library is switched off. Nothing else about the file is relevant.
2. **Out of schedule** — the library is on, but not right now.
3. **On hold** — the file is too new, or still settling.
4. **Blocked upstream** — a manager is still importing it.

Only a file that clears all four is unprocessed and eligible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.modules.refiner.refiner_file_state_model import RefinerFileRow, RefinerFileStatus
from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow
from mediamop.modules.refiner.refiner_operator_settings_service import (
    refiner_periodic_scope_in_schedule_window,
)


@dataclass(frozen=True, slots=True)
class FileStateVerdict:
    """A status and the sentence that explains it."""

    status: RefinerFileStatus
    reason: str
    blocked_by_connection: str | None = None

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
    size_is_settling: bool = False,
    blocked_by_connection: str | None = None,
) -> FileStateVerdict:
    """Why this file is or is not being worked on, in the order the reasons apply."""

    if not library.enabled:
        return FileStateVerdict(
            RefinerFileStatus.DISABLED,
            f"The {library.name} library is switched off, so MediaMop is leaving its files alone.",
        )

    if library.schedule_enabled and not in_schedule_window:
        return FileStateVerdict(
            RefinerFileStatus.OUT_OF_SCHEDULE,
            (
                f"The {library.name} library only runs inside its scheduled hours, and now is outside them. "
                "MediaMop will pick this up when the window opens."
            ),
        )

    hold_seconds = max(0, int(library.min_file_age_seconds)) + max(0, int(library.hold_minutes)) * 60
    if size_is_settling:
        return FileStateVerdict(
            RefinerFileStatus.ON_HOLD,
            "This file is still being written to, so MediaMop is waiting for it to finish before touching it.",
        )
    if hold_seconds and file_age_seconds is not None and file_age_seconds < hold_seconds:
        remaining = int(hold_seconds - file_age_seconds)
        return FileStateVerdict(
            RefinerFileStatus.ON_HOLD,
            (
                f"This file changed too recently. MediaMop waits {hold_seconds}s after the last change before "
                f"processing, so it has about {remaining}s to go."
            ),
        )

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


def library_in_schedule_window(session: Session, library: RefinerLibraryRow) -> bool:
    """Whether this library's schedule window is open right now.

    Falls back to the per-scope operator window while a library's own days and times are
    still seeded from it, so an upgrade does not silently change when work runs.
    """

    if not library.schedule_enabled:
        return True
    if not library.schedule_hours_limited:
        return True
    from mediamop.modules.refiner.refiner_operator_settings_service import (
        ensure_refiner_operator_settings_row,
    )

    row = ensure_refiner_operator_settings_row(session)
    return refiner_periodic_scope_in_schedule_window(session, row, media_scope=library.media_scope)


def record_file_state(
    session: Session,
    *,
    library: RefinerLibraryRow,
    relative_path: str,
    verdict: FileStateVerdict,
    size_bytes: int = 0,
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
    if size_bytes:
        row.size_bytes = int(size_bytes)
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
