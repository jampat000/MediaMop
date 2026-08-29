"""Singleton Refiner operator-editable automation settings (id = 1)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from mediamop.core.db import Base


class RefinerOperatorSettingsRow(Base):
    __tablename__ = "refiner_operator_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_refiner_operator_settings_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    max_concurrent_files: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    # A weighted budget replaces the flat count above: a 700 MB SD rip and a 60 GB 4K
    # remux are not the same unit of work, and a machine sized for two of the latter is
    # idle under six of the former. The count stays as the source the capacity was
    # migrated from, and as the per-library cap's units.
    runner_capacity: Mapped[int] = mapped_column(Integer, nullable=False, server_default="4")
    runner_cost_sd: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    runner_cost_720p: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    runner_cost_1080p: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    runner_cost_4k: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    runner_cost_undetermined: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # The sweeps stop being undocumented environment variables (#339).
    # Reclaiming MediaMop's own stale working files is safe, so it defaults on — a
    # default install never doing it is the bug this closes.
    work_temp_stale_sweep_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    # This one deletes source release folders after a terminal failure. Visible and
    # documented now, which it was not; still off until somebody chooses it.
    failure_cleanup_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    # Keep a failed run's working files so they can be inspected instead of swept.
    keep_failed_work_files: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")

    # The per-file processing record's own retention, independent of the suite log's:
    # diagnosing the application and diagnosing a file are different questions with
    # different lifetimes. 0 means keep forever.
    file_log_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="90")
    # Extra detail from the file-detection stage. Off by default, and meant to be turned
    # off again — it is loud, and that is the point of it.
    verbose_detection_logging: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")

    min_file_age_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default="60")
    refiner_min_input_file_size_mb: Mapped[int] = mapped_column(Integer, nullable=False, server_default="50")
    minimum_free_disk_space_mb: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5120")
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
