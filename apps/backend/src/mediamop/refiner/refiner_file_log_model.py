"""A durable record of what Refiner did to one file, and why.

Refiner's live telemetry is good — real percent and ETA per file while ffmpeg runs. What
it had no answer for is "why did this file come out like that, three weeks ago". Every
decision was already computed and put into an activity detail payload, and then aged out
under the suite's log retention along with everything else.

So this is a home for that payload with **its own retention**, because the two questions
have different lifetimes: a suite log is for diagnosing the application, and a per-file
record is for diagnosing a *file*, which someone may only ask about long after the fact.

One row per completed pass rather than one per file: a file that failed twice and then
succeeded has three things worth reading, and collapsing them would throw away exactly
the history that makes the record worth keeping.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from mediamop.core.db import Base


class RefinerFileLogRow(Base):
    """One completed Refiner pass over one file."""

    __tablename__ = "refiner_file_logs"
    __table_args__ = (
        Index("ix_refiner_file_logs_path", "relative_path"),
        Index("ix_refiner_file_logs_recorded_at", "recorded_at"),
        Index("ix_refiner_file_logs_file", "file_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Nullable, and deliberately ``SET NULL`` rather than ``CASCADE``: forgetting a file
    # from the Files screen must not destroy the record of what was done to it. That is
    # the opposite of why the record exists.
    file_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("refiner_files.id", ondelete="SET NULL"), nullable=True
    )
    library_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("refiner_libraries.id", ondelete="SET NULL"), nullable=True
    )
    # The path is stored flat as well as the ids, so a record stays readable after the
    # library it belonged to is gone.
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    library_name: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    outcome: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    title: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    #: The whole payload as JSON — admission decisions, probe, plan, argv, cleanup gates,
    #: timings, sizes. Kept whole rather than split into columns, because the shape is
    #: the pass's own and pinning it into a schema would make every future field a
    #: migration.
    detail_json: Mapped[str] = mapped_column(Text, nullable=False, server_default="{}")

    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
