"""Pydantic shapes for read-only Refiner runtime configuration (loaded settings, not liveness)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RefinerRuntimeVisibilityOut(BaseModel):
    """Settings-derived Refiner runtime **intent** — not a liveness or health report."""

    refiner_worker_count: int = Field(ge=0, le=8, description="Configured in-process asyncio worker tasks (0 disables).")
    in_process_workers_disabled: bool = Field(
        description="True when ``refiner_worker_count == 0`` (no worker tasks are intended).",
    )
    in_process_workers_enabled: bool = Field(
        description="True when ``refiner_worker_count >= 1`` (worker tasks are intended).",
    )
    worker_mode_summary: str = Field(
        description="Plain-language description of worker_count semantics (0 / 1 / >1).",
    )
    refiner_radarr_cleanup_drive_schedule_enabled: bool
    refiner_radarr_cleanup_drive_schedule_interval_seconds: int = Field(ge=60)
    refiner_sonarr_cleanup_drive_schedule_enabled: bool
    refiner_sonarr_cleanup_drive_schedule_interval_seconds: int = Field(ge=60)
    visibility_note: str = Field(
        description="Explicit caveat that this payload reflects configuration, not proved task health.",
    )
