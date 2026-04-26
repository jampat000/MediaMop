"""FastAPI application factory."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette import status

from mediamop import __version__
from mediamop.api.router import build_v1_router
from mediamop.core.config import MediaMopSettings
from mediamop.core.lifespan import lifespan
from mediamop.platform.health import health_router
from mediamop.platform.http.request_context import RequestContextMiddleware
from mediamop.platform.http.security_headers import SecurityHeadersMiddleware
from mediamop.platform.metrics.router import router as metrics_router


def _mount_web_spa_if_configured(application: FastAPI) -> None:
    """Serve the Vite production bundle from disk when ``MEDIAMOP_WEB_DIST`` is set (e.g. Docker all-in-one)."""
    raw = (os.environ.get("MEDIAMOP_WEB_DIST") or "").strip()
    if not raw:
        return
    root = Path(raw).expanduser().resolve()
    if not root.is_dir() or not (root / "index.html").is_file():
        return
    application.mount("/", StaticFiles(directory=str(root), html=True), name="web")


def _is_upgrade_browser_landing_404(request: Request, exc: StarletteHTTPException) -> bool:
    """Redirect stale/legacy in-app-upgrade browser landings back to the SPA.

    Older installed builds can leave the browser on an API-ish upgrade URL while the
    app restarts. Without this guard FastAPI returns ``{"detail":"Not Found"}``,
    which is technically correct but useless for a user during an upgrade.
    """

    if exc.status_code != status.HTTP_404_NOT_FOUND or request.method != "GET":
        return False
    path = request.url.path.lower()
    if not path.startswith("/api"):
        return False
    return any(token in path for token in ("update-now", "upgrade-now", "upgrade"))


def create_app() -> FastAPI:
    settings = MediaMopSettings.load()
    application = FastAPI(
        title="MediaMop API",
        version=__version__,
        lifespan=lifespan,
    )

    application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(RequestContextMiddleware)

    @application.exception_handler(StarletteHTTPException)
    async def _friendly_upgrade_landing_handler(request: Request, exc: StarletteHTTPException):
        if _is_upgrade_browser_landing_404(request, exc):
            return RedirectResponse(url="/app/settings", status_code=status.HTTP_303_SEE_OTHER)
        return await http_exception_handler(request, exc)

    if settings.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    application.include_router(health_router)
    application.include_router(metrics_router)
    application.include_router(build_v1_router())
    _mount_web_spa_if_configured(application)

    return application
