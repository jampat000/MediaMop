"""Pydantic shapes for read-only Refiner runtime configuration (loaded settings, not liveness)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RefinerRuntimeVisibilityOut(BaseModel):
    """Settings-derived Refiner runtime **intent** — not proof that workers or schedules are running."""

    refiner_worker_count: int = Field(ge=0, le=8, description="Configured background Refiner worker tasks (0 means workers off).")
    in_process_workers_disabled: bool = Field(
        description="True when worker count is 0 (no automatic pickup of queued jobs).",
    )
    in_process_workers_enabled: bool = Field(
        description="True when worker count is at least 1 (workers are intended to run).",
    )
    worker_mode_summary: str = Field(
        description="Plain-language description of worker_count semantics (0 / 1 / >1).",
    )
    refiner_radarr_cleanup_drive_schedule_enabled: bool
    refiner_radarr_cleanup_drive_schedule_interval_seconds: int = Field(ge=60)
    refiner_sonarr_cleanup_drive_schedule_enabled: bool
    refiner_sonarr_cleanup_drive_schedule_interval_seconds: int = Field(ge=60)
    visibility_note: str = Field(
        description="Caveat that values are from settings, not proof of live workers or *arr connectivity.",
    )
