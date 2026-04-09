"""Abuse controls wired to FastAPI requests (Phase 6)."""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from mediamop.platform.auth.rate_limit import client_rate_limit_key


def raise_if_login_rate_limited(request: Request) -> None:
    limiter = getattr(request.app.state, "auth_login_rate_limiter", None)
    settings = getattr(request.app.state, "settings", None)
    if limiter is None or settings is None:
        return
    if limiter.allow(client_rate_limit_key(request)):
        return
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many login attempts from this address. Try again later.",
        headers={"Retry-After": str(max(1, int(settings.auth_login_rate_window_seconds)))},
    )


def raise_if_bootstrap_rate_limited(request: Request) -> None:
    limiter = getattr(request.app.state, "bootstrap_rate_limiter", None)
    settings = getattr(request.app.state, "settings", None)
    if limiter is None or settings is None:
        return
    if limiter.allow(client_rate_limit_key(request)):
        return
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many bootstrap attempts from this address. Try again later.",
        headers={"Retry-After": str(max(1, int(settings.bootstrap_rate_window_seconds)))},
    )
