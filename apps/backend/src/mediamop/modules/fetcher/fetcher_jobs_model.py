"""Fetcher-local persisted job queue — durable background work (failed-import drives, future lanes)."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from mediamop.core.db import Base


class FetcherJobStatus(str, enum.Enum):
    """Persisted in ``fetcher_jobs.status`` (VARCHAR).

    ``handler_ok_finalize_failed`` means the handler ran without error but persisting
    ``completed`` (finalize) failed — distinct from ordinary failure, not re-runnable.
    """

    PENDING = "pending"
    LEASED = "leased"
    COMPLETED = "completed"
    FAILED = "failed"
    HANDLER_OK_FINALIZE_FAILED = "handler_ok_finalize_failed"


class FetcherJob(Base):
    """One row of durable Fetcher background work — claim/lease before execution."""

    __tablename__ = "fetcher_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dedupe_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    job_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text("'pending'"),
    )
    lease_owner: Mapped[str | None] = mapped_column(String(200), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("3"),
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
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
