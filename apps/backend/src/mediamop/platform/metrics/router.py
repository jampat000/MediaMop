"""Prometheus-style runtime metrics endpoint."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import PlainTextResponse

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.platform.auth import service as auth_service
from mediamop.platform.auth.models import UserRole
from mediamop.platform.metrics.service import render_prometheus_metrics

router = APIRouter(include_in_schema=False)


def _authorization_bearer_token(header_value: str | None) -> str | None:
    if not header_value:
        return None
    scheme, _, token = header_value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def require_metrics_access(
    request: Request,
    db: DbSessionDep,
    settings: SettingsDep,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    bearer_token = _authorization_bearer_token(authorization)
    expected_token = settings.metrics_bearer_token
    if bearer_token and expected_token and secrets.compare_digest(bearer_token, expected_token):
        return

    raw_session = (request.cookies.get(settings.session_cookie_name) or "").strip() or None
    pair = auth_service.load_valid_session_for_request(db, raw_session, settings)
    if pair is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
        )
    _row, user = pair
    if user.role not in {UserRole.admin.value, UserRole.operator.value}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden.",
        )


@router.get("/metrics", response_class=PlainTextResponse)
def get_metrics(_access: Annotated[None, Depends(require_metrics_access)]) -> PlainTextResponse:
    return PlainTextResponse(render_prometheus_metrics(), media_type="text/plain; version=0.0.4")
