"""Per-instance, per-axis (TV vs Movies) Pruner settings — denormalized latest preview summary."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mediamop.core.db import Base


class PrunerScopeSettings(Base):
    """Exactly one row per (server_instance_id, media_scope) — ``tv`` or ``movies``."""

    __tablename__ = "pruner_scope_settings"
    __table_args__ = (UniqueConstraint("server_instance_id", "media_scope", name="uq_pruner_scope_instance_scope"),)

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
    watched_tv_reported_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("0"),
    )
    watched_movies_reported_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("0"),
    )
    preview_max_items: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("500"),
    )
    preview_include_genres_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'[]'"),
    )
    preview_include_people_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'[]'"),
    )
    preview_include_people_roles_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'[\"cast\"]'"),
    )
    preview_year_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preview_year_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preview_include_studios_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'[]'"),
    )
    preview_include_collections_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'[]'"),
    )
    watched_movie_low_rating_reported_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("0"),
    )
    watched_movie_low_rating_max_jellyfin_emby_community_rating: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default=text("4.0"),
    )
    watched_movie_low_rating_max_plex_audience_rating: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default=text("4.0"),
    )
    unwatched_movie_stale_reported_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("0"),
    )
    unwatched_movie_stale_min_age_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("90"),
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
    scheduled_preview_hours_limited: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("0"),
    )
    scheduled_preview_days: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        server_default=text("''"),
    )
    scheduled_preview_start: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
        server_default=text("'00:00'"),
    )
    scheduled_preview_end: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
        server_default=text("'23:59'"),
    )
    last_scheduled_preview_enqueued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    auto_apply_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("0"),
    )
    max_deletes_per_run: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("50"),
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
