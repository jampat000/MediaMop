"""Per-instance, per-axis (TV vs Movies) Pruner settings — denormalized latest preview summary."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mediamop.core.db import Base


class PrunerScopeSettings(Base):
    """Exactly one row per (server_instance_id, media_scope) — ``tv`` or ``movies``."""

    __tablename__ = "pruner_scope_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    server_instance_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("pruner_server_instances.id", ondelete="CASCADE"),
        nullable=False,
    )
    media_scope: Mapped[str] = mapped_column(String(16), nullable=False)
    missing_primary_media_reported_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("1"),
    )
    never_played_stale_reported_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("0"),
    )
    never_played_min_age_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("90"),
    )
    preview_max_items: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("500"),
    )
    last_preview_run_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("pruner_preview_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_preview_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_preview_candidate_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_preview_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_preview_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_preview_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("0"),
    )
    scheduled_preview_interval_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("3600"),
    )
    last_scheduled_preview_enqueued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    server_instance: Mapped["PrunerServerInstance"] = relationship(
        "PrunerServerInstance",
        back_populates="scope_settings",
    )
