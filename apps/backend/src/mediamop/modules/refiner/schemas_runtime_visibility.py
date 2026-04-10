"""Pydantic shapes for read-only runner + schedule settings (loaded from config, not liveness).

Exposed on **Fetcher** ``GET /api/v1/fetcher/failed-imports/settings`` for the download-queue failed-import
workflow; field names keep ``refiner_*`` prefixes because they map to existing settings keys.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RefinerRuntimeVisibilityOut(BaseModel):
    """Settings-derived intent for queued task runners — not proof that runners or timed passes are active."""

    refiner_worker_count: int = Field(
        ge=0,
        le=8,
        description="Configured in-process runner count for queued tasks (0 means none).",
    )
    in_process_workers_disabled: bool = Field(
        description="True when runner count is 0 (queued tasks will not start automatically).",
    )
    in_process_workers_enabled: bool = Field(
        description="True when at least one runner is configured to process queued tasks.",
    )
    worker_mode_summary: str = Field(
        description="Plain-language summary of runner count semantics (0 / 1 / >1).",
    )
    refiner_radarr_cleanup_drive_schedule_enabled: bool
    refiner_radarr_cleanup_drive_schedule_interval_seconds: int = Field(ge=60)
    refiner_sonarr_cleanup_drive_schedule_enabled: bool
    refiner_sonarr_cleanup_drive_schedule_interval_seconds: int = Field(ge=60)
    visibility_note: str = Field(
        description="Caveat: from settings only — not proof of live runners, timed passes, or app connectivity.",
    )
