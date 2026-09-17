"""API composition — versioned JSON product surface.

Convention (locked in Phase 3):

- **Operational health**: ``GET /health`` at the **application root** (probe-friendly, no version prefix).
- **Product JSON API**: browser- and integration-facing JSON routes under **``/api/v1``**
  (mounted via :func:`build_v1_router`). Do not add unversioned product paths at root.

Routers (auth, refiner, activity, pause, …) are composed under ``/api/v1`` here.
"""

from __future__ import annotations

from fastapi import APIRouter

from weir.platform.activity.router import router as activity_router
from weir.platform.auth.router import router as auth_router
from weir.platform.local_browse.router import router as local_browse_router
from weir.platform.media_managers.connections_api import router as media_manager_connections_router
from weir.platform.media_managers.intake_api import router as media_manager_intake_router
from weir.platform.notifications.router import router as notifications_router
from weir.platform.pause.api import router as pause_router
from weir.platform.reconciliation.router import router as reconciliation_router
from weir.platform.suite_settings.router import router as suite_settings_router
from weir.platform.system_configuration.router import router as system_configuration_router
from weir.refiner.router import router as refiner_router

API_V1_PREFIX = "/api/v1"


def build_v1_router() -> APIRouter:
    """Version 1 API — auth boundary under ``/api/v1/auth`` (Phase 5)."""
    router = APIRouter(prefix=API_V1_PREFIX)
    router.include_router(auth_router)
    router.include_router(system_configuration_router)
    router.include_router(local_browse_router)
    router.include_router(reconciliation_router)
    router.include_router(suite_settings_router)
    router.include_router(pause_router)
    router.include_router(activity_router)
    router.include_router(refiner_router)
    router.include_router(media_manager_intake_router)
    router.include_router(media_manager_connections_router)
    router.include_router(notifications_router)
    return router
