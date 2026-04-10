"""Pydantic shapes for read-only Refiner job inspection API responses."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RefinerJobInspectionRow(BaseModel):
    """One row for operators — status is the persisted string (e.g. ``handler_ok_finalize_failed``)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    dedupe_key: str
    job_kind: str
    status: str = Field(description="Persisted status string for this queue row.")
    attempt_count: int
    max_attempts: int
    lease_owner: str | None
    lease_expires_at: datetime | None
    last_error: str | None
    payload_json: str | None = None
    created_at: datetime
    updated_at: datetime


class RefinerJobsInspectionOut(BaseModel):
    """Bounded list ordered by ``updated_at`` descending."""

    jobs: list[RefinerJobInspectionRow]
    default_terminal_only: bool = Field(
        description="True when no ``status`` filter was applied (only terminal rows: completed, failed, handler_ok_finalize_failed).",
    )
