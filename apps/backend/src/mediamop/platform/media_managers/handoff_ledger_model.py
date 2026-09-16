"""One row per hand-off a media manager gave MediaMop (#480).

Job rows are pruned after a week and by "clear history", and the hand-off id only ever lived on
a job's payload. A manager asking "what happened to the file I gave you?" a month later would
then hear "never heard of it" — which Deluno reads as a reason to import the unprocessed original.
This row outlives the job so that answer is never given wrongly.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from mediamop.core.db import Base


class MediaManagerHandoffRow(Base):
    __tablename__ = "media_manager_handoffs"
    __table_args__ = (UniqueConstraint("source_key", "handoff_id", name="uq_media_manager_handoffs_source_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_key: Mapped[str] = mapped_column(Text, nullable=False)
    handoff_id: Mapped[str] = mapped_column(Text, nullable=False)
    library_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("refiner_libraries.id", ondelete="SET NULL"), nullable=True
    )
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    #: The last state MediaMop worked out or recorded, in the manager-facing vocabulary.
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default="queued")
    output_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
