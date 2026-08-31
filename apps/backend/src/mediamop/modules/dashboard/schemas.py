"""Pydantic models for ``GET /api/v1/dashboard/status``."""

from __future__ import annotations

from pydantic import BaseModel, Field

from mediamop.platform.activity.schemas import ActivityEventItemOut


class WorkerLaneHealthOut(BaseModel):
    module: str
    expected_workers: int = Field(..., ge=0)
    active_workers: int = Field(..., ge=0)
    stale_workers: int = Field(..., ge=0)
    stopped_workers: int = Field(..., ge=0)
    status: str = Field(..., description="healthy, degraded, or disabled.")
    detail: str


class SystemStatusOut(BaseModel):
    api_version: str = Field(..., description="MediaMop API package version.")
    environment: str = Field(..., description="MEDIAMOP_ENV value.")
    healthy: bool = Field(..., description="Process liveness (same signal as GET /health).")
    worker_health: list[WorkerLaneHealthOut] = Field(default_factory=list)


class ModuleOperationalStatusOut(BaseModel):
    """Current module state, deliberately separate from historical counters."""

    module: str
    state: str = Field(description="setup_required, processing, degraded, paused, or healthy.")
    configured: bool
    active_job_count: int = Field(default=0, ge=0)
    queued_job_count: int = Field(default=0, ge=0)
    failed_job_count: int = Field(default=0, ge=0)
    quarantined_file_count: int = Field(default=0, ge=0)
    summary: str
    action_path: str


class ActivitySummaryOut(BaseModel):
    """Derived from persisted ``activity_events`` only — snapshot at request time."""

    events_last_24h: int = Field(..., ge=0, description="Count of rows with created_at in the last 24 hours.")
    latest: ActivityEventItemOut | None = Field(None, description="Newest event of any type, if any.")


class DashboardStatusOut(BaseModel):
    scope_note: str = Field(
        default="Read-only overview. No jobs or settings are changed from this view.",
        description="Fixed honesty line for the dashboard slice.",
    )
    system: SystemStatusOut
    activity_summary: ActivitySummaryOut
    modules: list[ModuleOperationalStatusOut] = Field(default_factory=list)
    incident_count: int = Field(default=0, ge=0)
