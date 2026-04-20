"""FastAPI application factory."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from mediamop import __version__
from mediamop.api.router import build_v1_router
from mediamop.core.config import MediaMopSettings
from mediamop.core.lifespan import lifespan
from mediamop.platform.health import health_router
from mediamop.platform.http.security_headers import SecurityHeadersMiddleware


def _mount_web_spa_if_configured(application: FastAPI) -> None:
    """Serve the Vite production bundle from disk when ``MEDIAMOP_WEB_DIST`` is set (e.g. Docker all-in-one)."""
    raw = (os.environ.get("MEDIAMOP_WEB_DIST") or "").strip()
    if not raw:
        return
    root = Path(raw).expanduser().resolve()
    if not root.is_dir() or not (root / "index.html").is_file():
        return
    application.mount("/", StaticFiles(directory=str(root), html=True), name="web")


def create_app() -> FastAPI:
    settings = MediaMopSettings.load()
    application = FastAPI(
        title="MediaMop API",
        version=__version__,
        lifespan=lifespan,
    )

    application.add_middleware(SecurityHeadersMiddleware)
    if settings.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    application.include_router(health_router)
    application.include_router(build_v1_router())
    _mount_web_spa_if_configured(application)

    return application
