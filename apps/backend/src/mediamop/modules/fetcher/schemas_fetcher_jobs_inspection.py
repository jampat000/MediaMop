"""Pydantic shapes for read-only ``fetcher_jobs`` listings (Fetcher jobs inspection API)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FetcherJobInspectionRow(BaseModel):
    """One persisted Fetcher background job row."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    dedupe_key: str
    job_kind: str
    status: str = Field(description="Persisted status value for this row.")
    attempt_count: int
    max_attempts: int
    lease_owner: str | None
    lease_expires_at: datetime | None
    last_error: str | None
    payload_json: str | None = None
    created_at: datetime
    updated_at: datetime


class FetcherJobsInspectionOut(BaseModel):
    """Bounded list of persisted Fetcher job rows, newest activity first."""

    jobs: list[FetcherJobInspectionRow]
    default_terminal_only: bool = Field(
        description="True when no ``status`` filter was applied (only terminal rows: completed, failed, handler_ok_finalize_failed).",
    )
