"""Singleton row for names and notices shown across the signed-in app (not Sonarr/Radarr)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from mediamop.core.db import Base


class SuiteSettingsRow(Base):
    """One row (``id = 1``) — product name and optional home notice for operators."""

    __tablename__ = "suite_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_suite_settings_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_display_name: Mapped[str] = mapped_column(Text, nullable=False, server_default="MediaMop")
    signed_in_home_notice: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
