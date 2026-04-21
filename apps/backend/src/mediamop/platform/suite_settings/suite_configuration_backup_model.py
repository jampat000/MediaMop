"""Stored automatic suite configuration snapshots."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from mediamop.core.db import Base


class SuiteConfigurationBackupRow(Base):
    """Metadata row for one on-disk configuration snapshot JSON file."""

    __tablename__ = "suite_configuration_backup"
    __table_args__ = (UniqueConstraint("file_name", name="uq_suite_configuration_backup_file_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
