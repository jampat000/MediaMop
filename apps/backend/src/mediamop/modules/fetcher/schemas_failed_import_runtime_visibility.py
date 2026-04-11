"""Pydantic shapes for read-only failed-import automation settings (from config, not liveness).

Exposed on ``GET /api/v1/fetcher/failed-imports/settings``. ``background_job_worker_count`` is the
configured in-process worker pool that processes ``refiner_jobs`` (including failed-import drives).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class FailedImportRuntimeVisibilityOut(BaseModel):
    """Settings-derived intent for failed-import automation — not live runner or *arr health."""

    background_job_worker_count: int = Field(
        ge=0,
        le=8,
        description="Configured in-process worker count for queued background jobs (0 means none).",
    )
    in_process_workers_disabled: bool = Field(
        description="True when worker count is 0 (queued tasks will not start automatically).",
    )
    in_process_workers_enabled: bool = Field(
        description="True when at least one worker is configured to process queued tasks.",
    )
    worker_mode_summary: str = Field(
        description="Plain-language summary of worker count semantics (0 / 1 / >1).",
    )
    failed_import_radarr_cleanup_drive_schedule_enabled: bool
    failed_import_radarr_cleanup_drive_schedule_interval_seconds: int = Field(ge=60)
    failed_import_sonarr_cleanup_drive_schedule_enabled: bool
    failed_import_sonarr_cleanup_drive_schedule_interval_seconds: int = Field(ge=60)
    visibility_note: str = Field(
        description="Caveat: from settings only — not proof of live workers, timed passes, or app connectivity.",
    )
