"""What Refiner thinks about one file, including the reasons it is *not* working on it.

Refiner had one vocabulary: a job is pending, leased, completed or failed. None of those
can say "this file qualifies but its library is switched off", or "its schedule window
closed", or "the manager that owns it is still importing it". So an operator asking why a
file is not processing had nowhere to look — the scan simply did not enqueue it, and the
reason existed only as a local variable.

A file is a row now, and every state carries a sentence written for the person reading it
rather than for the code that set it.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from mediamop.core.db import Base


class RefinerFileStatus(StrEnum):
    """The vocabulary an operator sees on the Files screen.

    The first four mirror what job rows already expressed. The last four are the point of
    this type: each is a deliberate decision *not* to process a file, and each was
    previously invisible.
    """

    UNPROCESSED = "unprocessed"
    PROCESSING = "processing"
    PROCESSED = "processed"
    PROCESSING_FAILED = "processing_failed"
    DISABLED = "disabled"
    ON_HOLD = "on_hold"
    OUT_OF_SCHEDULE = "out_of_schedule"
    BLOCKED_UPSTREAM = "blocked_upstream"


#: States where MediaMop has decided not to act, as opposed to not having acted yet.
REFINER_WITHHELD_STATUSES: frozenset[str] = frozenset(
    {
        RefinerFileStatus.DISABLED.value,
        RefinerFileStatus.ON_HOLD.value,
        RefinerFileStatus.OUT_OF_SCHEDULE.value,
        RefinerFileStatus.BLOCKED_UPSTREAM.value,
    }
)


class RefinerFileRow(Base):
    """One file Refiner has seen, and the last thing it decided about it."""

    __tablename__ = "refiner_files"
    __table_args__ = (
        UniqueConstraint("library_id", "relative_path", name="uq_refiner_files_library_path"),
        Index("ix_refiner_files_status", "status"),
        Index("ix_refiner_files_library_status", "library_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    library_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("refiner_libraries.id", ondelete="CASCADE"), nullable=False
    )
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=RefinerFileStatus.UNPROCESSED.value)
    # Always operator-facing prose. A status with no reason is a status that cannot
    # answer the question the screen exists to answer.
    status_reason: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # Set only for BLOCKED_UPSTREAM: the connection holding the file, named the way the
    # blocked-upstream reasons name it — never the vendor.
    blocked_by_connection: Mapped[str | None] = mapped_column(Text, nullable=True)

    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    # Recorded after a pass has probed the file, and read at the *next* enqueue to weight
    # it. Null until then, which costs the "undetermined" weight rather than a guess.
    # Width is the one that decides the class: 1920x800 is a scope crop of a 1080p master,
    # and height alone cannot tell it from 1280x720.
    video_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    video_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # When ``size_bytes`` last differed from the previous observation. Null until a
    # second scan has something to compare against.
    size_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # When an ON_HOLD file becomes eligible. Held without a release time reads as held
    # forever, which is the complaint the Files screen exists to answer.
    hold_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
