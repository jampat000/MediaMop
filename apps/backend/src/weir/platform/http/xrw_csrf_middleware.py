"""Lightweight CSRF defence via ``X-Requested-With: XMLHttpRequest``.

All state-mutating API requests (POST/PUT/PATCH/DELETE to ``/api/``) must include this
header. Browsers block custom headers in cross-origin requests without a prior CORS
preflight, so their absence means the request cannot have originated from a regular web
page on a different origin.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# No exempt paths: the only ones were the Subber webhooks, and Subber has gone to Deluno.
_EXEMPT_PREFIXES: tuple[str, ...] = ()


class XRequestedWithCsrfMiddleware(BaseHTTPMiddleware):
    """Reject mutating API requests that omit ``X-Requested-With: XMLHttpRequest``."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method in _MUTATING_METHODS and request.url.path.startswith("/api/"):
            for prefix in _EXEMPT_PREFIXES:
                if request.url.path.startswith(prefix):
                    return await call_next(request)
            # CSRF attacks require a browser, which always sends Origin. Direct API calls
            # (curl, test clients, server-to-server) don't send Origin — no CSRF risk.
            if request.headers.get("Origin") is None:
                return await call_next(request)
            xrw = (request.headers.get("X-Requested-With") or "").strip()
            if xrw.lower() != "xmlhttprequest":
                return JSONResponse(
                    {
                        "detail": "Missing X-Requested-With header. This endpoint requires an authenticated browser session."
                    },
                    status_code=403,
                )
        return await call_next(request)
