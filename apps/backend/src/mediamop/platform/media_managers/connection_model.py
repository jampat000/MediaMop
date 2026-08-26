"""Media manager connections and their search lanes (SQLite).

The previous shape was a singleton row with every column written twice — once
``sonarr_``-prefixed and once ``radarr_`` — for connections and for each of four
search lanes. Adding a third manager meant another forty columns, which is why there
never was a third.

A connection is now a row. Its kind says which dialect it speaks; its lanes are rows
too, so "missing" and "upgrade" stop being column-name prefixes.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mediamop.core.db import Base

# Kinds that have a payload dialect in mediamop.platform.media_managers.import_events.
MEDIA_MANAGER_KINDS: tuple[str, ...] = ("radarr", "sonarr", "deluno", "native")

# A lane is an automatic search pass over the manager's library.
SEARCH_LANES: tuple[str, ...] = ("missing", "upgrade")


class MediaManagerConnectionRow(Base):
    """One configured media manager."""

    __tablename__ = "media_manager_connections"
    __table_args__ = (UniqueConstraint("name", name="uq_media_manager_connections_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    base_url: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    api_key_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Inbound secret for this manager's own webhook posts. Per connection rather than
    # one global value, so revoking one manager's access does not lock out the others.
    webhook_secret_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)

    last_connection_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_connection_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_connection_test_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    lanes: Mapped[list[MediaManagerSearchLaneRow]] = relationship(
        back_populates="connection",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class MediaManagerSearchLaneRow(Base):
    """One automatic search lane belonging to a connection."""

    __tablename__ = "media_manager_search_lanes"
    __table_args__ = (UniqueConstraint("connection_id", "lane", name="uq_media_manager_search_lanes_connection_lane"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connection_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("media_manager_connections.id", ondelete="CASCADE"), nullable=False
    )
    lane: Mapped[str] = mapped_column(Text, nullable=False)

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    max_items_per_run: Mapped[int] = mapped_column(Integer, nullable=False, server_default="50")
    retry_delay_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1440")
    schedule_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    schedule_days: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    schedule_start: Mapped[str] = mapped_column(Text, nullable=False, server_default="00:00")
    schedule_end: Mapped[str] = mapped_column(Text, nullable=False, server_default="23:59")
    schedule_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3600")

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    connection: Mapped[MediaManagerConnectionRow] = relationship(back_populates="lanes")
