"""HTTP surface for process health — mounted at app root ``/health`` (not under ``/api/v1``)."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from mediamop.platform.health.schemas import HealthResponse
from mediamop.platform.health.service import get_health

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request, response: Response) -> HealthResponse:
    payload = get_health(request.app.state)
    if payload.status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return payload
