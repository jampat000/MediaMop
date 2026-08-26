"""Subber HTTP routes — operator APIs under ``/api/v1/subber``.

Inbound media-manager events arrive at ``/api/v1/intake/webhook/{source}`` instead;
see :mod:`mediamop.platform.media_managers.intake_api`."""

from __future__ import annotations

from fastapi import APIRouter

from mediamop.modules.subber.subber_jobs_inspection_api import router as subber_jobs_inspection_router
from mediamop.modules.subber.subber_library_api import router as subber_library_router
from mediamop.modules.subber.subber_providers_api import router as subber_providers_router
from mediamop.modules.subber.subber_settings_api import router as subber_settings_router

router = APIRouter(prefix="/subber", tags=["subber"])
router.include_router(subber_settings_router)
router.include_router(subber_providers_router)
router.include_router(subber_library_router)
router.include_router(subber_jobs_inspection_router)
