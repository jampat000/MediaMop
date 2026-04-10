"""Schemas for read-only Fetcher operational overview."""

from __future__ import annotations

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


class FetcherOperationalOverviewOut(BaseModel):
    """Read-mostly operational slice from current probe + persisted probe events."""

    mediamop_version: str = Field(..., description="MediaMop API package version for this shell.")
    status_label: str = Field(..., description="One-line operational status for current Fetcher connectivity.")
    status_detail: str = Field(..., description="Short operator-facing explanation of current status.")
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
