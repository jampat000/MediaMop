"""Schemas for read-only Fetcher operational overview."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from mediamop.platform.activity.schemas import ActivityEventItemOut


class FetcherProbePersistedWindowOut(BaseModel):
    """Aggregates over persisted probe rows only (throttled writes, not raw /healthz attempts)."""

    window_hours: int = Field(24, description="Rolling window width for the snapshot.")
    persisted_ok: int = Field(..., ge=0, description="Rows with fetcher.probe_succeeded in the window.")
    persisted_failed: int = Field(..., ge=0, description="Rows with fetcher.probe_failed in the window.")


class FetcherConnectionOut(BaseModel):
    configured: bool
    target_display: str | None = None
    reachable: bool | None = None
    http_status: int | None = None
    latency_ms: float | None = None
    fetcher_app: str | None = None
    fetcher_version: str | None = None
    detail: str | None = None


class FetcherFailedImportAutomationLaneOut(BaseModel):
    """Read-only summary row for one failed-import automation lane."""

    last_finished_at: datetime | None = Field(
        None,
        description="Newest persisted terminal row timestamp for this lane (completed/failed/manual-finish-needed).",
    )
    last_outcome: str | None = Field(
        None,
        description="Plain label for the last finished row outcome, or null when none exists.",
    )
    saved_schedule: str = Field(..., description="Saved schedule framing only (for example 'Off' or 'Every 1 hour').")
    next_run_note: str = Field(
        ...,
        description="Honest next-run wording from saved settings only (no live scheduler claim).",
    )


class FetcherFailedImportAutomationSummaryOut(BaseModel):
    """Read-only persisted automation summary for failed-import cleanup lanes."""

    movies: FetcherFailedImportAutomationLaneOut
    tv_shows: FetcherFailedImportAutomationLaneOut
    source_note: str = Field(
        ...,
        description="Clarifies this summary comes from persisted history + saved settings, not live workers.",
    )


class FetcherOperationalOverviewOut(BaseModel):
    """Read-mostly operational slice from current probe + persisted probe events."""

    mediamop_version: str = Field(..., description="MediaMop API package version for this shell.")
    status_label: str = Field(..., description="One-line operational status for current Fetcher connectivity.")
    status_detail: str = Field(..., description="Short operator-facing explanation of current status.")
    failed_import_automation: FetcherFailedImportAutomationSummaryOut
    connection: FetcherConnectionOut
    probe_persisted_24h: FetcherProbePersistedWindowOut
    probe_failure_window_days: int = Field(
        7,
        description="Rolling window width for recent_probe_failures (persisted failures only).",
    )
    recent_probe_failures: list[ActivityEventItemOut] = Field(
        default_factory=list,
        description="Newest persisted fetcher.probe_failed rows in the window, capped in the service.",
    )
    latest_probe_event: ActivityEventItemOut | None = None
    recent_probe_events: list[ActivityEventItemOut] = Field(default_factory=list)
