"""Singleton row for suite-level Settings fields shown across the signed-in app."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from mediamop.core.db import Base


class SuiteSettingsRow(Base):
    """One row (``id = 1``) — suite-owned global settings only."""

    __tablename__ = "suite_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_suite_settings_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_display_name: Mapped[str] = mapped_column(Text, nullable=False, server_default="MediaMop")
    signed_in_home_notice: Mapped[str | None] = mapped_column(Text, nullable=True)
    app_timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default="UTC")
    log_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="30")
    configuration_backup_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    configuration_backup_interval_hours: Mapped[int] = mapped_column(Integer, nullable=False, server_default="24")
    configuration_backup_last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
