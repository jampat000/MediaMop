"""Persisted activity events for the read-only Activity feed."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from mediamop.core.db import Base


class ActivityEvent(Base):
    """One row per surfaced platform event — narrow fields only, no generic JSON payload."""

    __tablename__ = "activity_events"
    __table_args__ = (
        Index("ix_activity_events_created_at", "created_at"),
        Index("ix_activity_events_module", "module"),
        Index("ix_activity_events_relative_path", "relative_path"),
        Index("ix_activity_events_run_key", "run_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    module: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Lifted from the detail when the event is written, so history can be filtered (#469).
    # See ``mediamop.platform.activity.classify``; empty means the producer did not say.
    trigger: Mapped[str | None] = mapped_column(String(32), nullable=True)
    result: Mapped[str | None] = mapped_column(String(16), nullable=True)
    library_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    relative_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
