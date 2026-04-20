"""Broker *arr connection rows (Sonarr / Radarr) — Broker-owned."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from mediamop.core.db import Base


class BrokerArrConnectionRow(Base):
    """Stored Sonarr/Radarr API targets for indexer sync."""

    __tablename__ = "broker_arr_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    arr_type: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    url: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    api_key: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    sync_mode: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'full'"),
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_ok: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_manual_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_manual_sync_ok: Mapped[int | None] = mapped_column(Integer, nullable=True)
    indexer_fingerprint: Mapped[str | None] = mapped_column(Text, nullable=True)
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
