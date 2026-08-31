"""Readiness endpoint mounted at app root."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from mediamop.platform.auth.deps_auth import UserPublicDep
from mediamop.platform.readiness.schemas import PublicReadinessResponse, ReadinessResponse
from mediamop.platform.readiness.service import build_readiness

router = APIRouter(tags=["readiness"])


@router.get("/ready", response_model=PublicReadinessResponse)
def ready(request: Request, response: Response) -> PublicReadinessResponse:
    payload = build_readiness(request.app.state)
    if not payload.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return PublicReadinessResponse(ready=payload.ready, status=payload.status)


@router.get("/api/v1/system/readiness", response_model=ReadinessResponse)
def authenticated_readiness(request: Request, response: Response, _user: UserPublicDep) -> ReadinessResponse:
    """Detailed startup and worker diagnostics for signed-in operators."""

    payload = build_readiness(request.app.state)
    if not payload.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return payload
