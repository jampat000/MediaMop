"""Readiness endpoint mounted at app root."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from mediamop.platform.readiness.schemas import ReadinessResponse
from mediamop.platform.readiness.service import build_readiness

router = APIRouter(tags=["readiness"])


@router.get("/ready", response_model=ReadinessResponse)
def ready(request: Request, response: Response) -> ReadinessResponse:
    payload = build_readiness(request.app.state)
    if not payload.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return payload
