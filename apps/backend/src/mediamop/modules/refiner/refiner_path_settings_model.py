"""Persisted Refiner path roles (watched / work / output) — singleton ``id = 1``.

Refiner-owned persistence; not a suite-wide ``app_settings`` table. Manual remux and future
Refiner families read these columns (no ongoing environment fallback for path resolution).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from mediamop.core.db import Base


class RefinerPathSettingsRow(Base):
    __tablename__ = "refiner_path_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_refiner_path_settings_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    refiner_watched_folder: Mapped[str | None] = mapped_column(Text, nullable=True)
    refiner_work_folder: Mapped[str | None] = mapped_column(Text, nullable=True)
    refiner_output_folder: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    refiner_tv_watched_folder: Mapped[str | None] = mapped_column(Text, nullable=True)
    refiner_tv_work_folder: Mapped[str | None] = mapped_column(Text, nullable=True)
    refiner_tv_output_folder: Mapped[str | None] = mapped_column(Text, nullable=True)
    movie_watched_folder_check_interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="300"
    )
    tv_watched_folder_check_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="300")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
