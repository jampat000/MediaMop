"""Singleton Refiner operator-editable automation settings (id = 1)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from mediamop.core.db import Base


class RefinerOperatorSettingsRow(Base):
    __tablename__ = "refiner_operator_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_refiner_operator_settings_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    max_concurrent_files: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    min_file_age_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="60")
    movie_schedule_enabled: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    movie_schedule_hours_limited: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    movie_schedule_days: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    movie_schedule_start: Mapped[str] = mapped_column(Text, nullable=False, server_default="00:00")
    movie_schedule_end: Mapped[str] = mapped_column(Text, nullable=False, server_default="23:59")
    tv_schedule_enabled: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    tv_schedule_hours_limited: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    tv_schedule_days: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    tv_schedule_start: Mapped[str] = mapped_column(Text, nullable=False, server_default="00:00")
    tv_schedule_end: Mapped[str] = mapped_column(Text, nullable=False, server_default="23:59")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
