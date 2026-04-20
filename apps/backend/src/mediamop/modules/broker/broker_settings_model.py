"""Singleton Broker operator settings (proxy API key)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from mediamop.core.db import Base


class BrokerSettingsRow(Base):
    """Single-row table ``broker_settings`` (``id`` must be 1)."""

    __tablename__ = "broker_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    proxy_api_key: Mapped[str] = mapped_column(Text, nullable=False)
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
