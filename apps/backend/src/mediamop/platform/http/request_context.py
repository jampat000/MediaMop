"""Per-request context shared with logging and runtime metrics."""

from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar, Token
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from mediamop.platform.metrics.service import record_http_request

_request_id_var: ContextVar[str | None] = ContextVar("mediamop_request_id", default=None)
_job_id_var: ContextVar[str | None] = ContextVar("mediamop_job_id", default=None)


def current_request_id() -> str | None:
    return _request_id_var.get()


def current_job_id() -> str | None:
    return _job_id_var.get()


@contextmanager
def job_logging_context(job_id: str | int | None):
    token = _job_id_var.set(str(job_id) if job_id is not None else None)
    try:
        yield
    finally:
        _job_id_var.reset(token)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Adds ``X-Request-ID`` and records runtime request metrics."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = (request.headers.get("X-Request-ID") or "").strip() or uuid4().hex
        request_token: Token[str | None] = _request_id_var.set(request_id)
        job_token: Token[str | None] = _job_id_var.set(None)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started) * 1000
            record_http_request(
                method=request.method,
                route=_route_label(request),
                status_code=500,
                duration_ms=duration_ms,
            )
            _job_id_var.reset(job_token)
            _request_id_var.reset(request_token)
            raise

        duration_ms = (time.perf_counter() - started) * 1000
        record_http_request(
            method=request.method,
            route=_route_label(request),
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        response.headers["X-Request-ID"] = request_id
        _job_id_var.reset(job_token)
        _request_id_var.reset(request_token)
        return response


def _route_label(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None:
        path = getattr(route, "path", None)
        if isinstance(path, str) and path.strip():
            return path
    return request.url.path
