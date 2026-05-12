"""SQLAlchemy model for outbound notification channels."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from mediamop.core.db import Base

SUPPORTED_EVENTS = (
    "job_completed",
    "job_failed",
    "refiner_job_completed",
    "refiner_job_failed",
    "pruner_job_completed",
    "pruner_job_failed",
    "subber_job_completed",
    "subber_job_failed",
)

SUPPORTED_PROVIDERS = ("webhook", "discord")


class NotificationChannel(Base):
    """One outbound notification destination."""

    __tablename__ = "notification_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    events_json: Mapped[str] = mapped_column(Text, nullable=False, server_default='["job_failed"]')
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
