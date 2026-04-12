"""API composition — versioned JSON product surface.

Convention (locked in Phase 3):

- **Operational health**: ``GET /health`` at the **application root** (probe-friendly, no version prefix).
- **Product JSON API**: all future browser- and integration-facing JSON routes under **``/api/v1``**
  (mounted via :func:`build_v1_router`). Do not add unversioned product paths at root.

Module routers (fetcher/refiner/etc.) will be included under ``/api/v1`` in later phases — not in the nested ``mediamop/`` Jinja app.
"""

from __future__ import annotations

from fastapi import APIRouter

from mediamop.modules.dashboard.router import router as dashboard_router
from mediamop.modules.fetcher.router import router as fetcher_router
from mediamop.modules.refiner.router import router as refiner_router
from mediamop.modules.subber.router import router as subber_router
from mediamop.modules.trimmer.router import router as trimmer_router
from mediamop.platform.activity.router import router as activity_router
from mediamop.platform.auth.router import router as auth_router

API_V1_PREFIX = "/api/v1"


def build_v1_router() -> APIRouter:
    """Version 1 API — auth boundary under ``/api/v1/auth`` (Phase 5)."""
    router = APIRouter(prefix=API_V1_PREFIX)
    router.include_router(auth_router)
    router.include_router(dashboard_router)
    router.include_router(fetcher_router)
    router.include_router(activity_router)
    router.include_router(refiner_router)
    router.include_router(trimmer_router)
    router.include_router(subber_router)
    return router
