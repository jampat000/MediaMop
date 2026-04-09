"""HTTP surface for process health — mounted at app root ``/health`` (not under ``/api/v1``)."""

from __future__ import annotations

from fastapi import APIRouter

from mediamop.platform.health.schemas import HealthResponse
from mediamop.platform.health.service import get_health

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return get_health()
