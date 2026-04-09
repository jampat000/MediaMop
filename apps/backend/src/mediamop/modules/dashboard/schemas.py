"""Pydantic models for ``GET /api/v1/dashboard/status``."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SystemStatusOut(BaseModel):
    api_version: str = Field(..., description="MediaMop API package version.")
    environment: str = Field(..., description="MEDIAMOP_ENV value.")
    healthy: bool = Field(..., description="Process liveness (same signal as GET /health).")


class FetcherIntegrationOut(BaseModel):
    configured: bool = Field(
        ...,
        description="True when MEDIAMOP_FETCHER_BASE_URL is set to an http(s) origin.",
    )
    target_display: str | None = Field(
        None,
        description="Sanitized origin (scheme + host[:port]) for display; null when not configured.",
    )
    reachable: bool | None = Field(
        None,
        description="Result of last GET {target}/healthz probe; null when not configured.",
    )
    http_status: int | None = Field(None, description="HTTP status from healthz when probed.")
    latency_ms: float | None = Field(None, description="Round-trip time for healthz when reachable.")
    fetcher_app: str | None = Field(None, description="`app` field from Fetcher healthz JSON when present.")
    fetcher_version: str | None = Field(
        None,
        description="`version` field from Fetcher healthz JSON when present.",
    )
    detail: str | None = Field(
        None,
        description="Short error text when unreachable or misconfigured; not a stack trace.",
    )


class DashboardStatusOut(BaseModel):
    scope_note: str = Field(
        default="Read-only overview. No jobs or settings are changed from this view.",
        description="Fixed honesty line for the dashboard slice.",
    )
    system: SystemStatusOut
    fetcher: FetcherIntegrationOut
