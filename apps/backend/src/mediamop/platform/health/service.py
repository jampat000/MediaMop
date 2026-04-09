"""Health domain logic — keep free of database and auth coupling."""

from __future__ import annotations

from mediamop.platform.health.schemas import HealthResponse


def get_health() -> HealthResponse:
    """Return current process liveness. No dependency checks in Phase 3."""
    return HealthResponse(status="ok")
