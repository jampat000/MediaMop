"""Subber HTTP routes — operator APIs and unauthenticated *arr webhooks under ``/api/v1/subber``."""

from __future__ import annotations

from fastapi import APIRouter

from mediamop.modules.subber.subber_jobs_inspection_api import router as subber_jobs_inspection_router
from mediamop.modules.subber.subber_library_api import router as subber_library_router
from mediamop.modules.subber.subber_settings_api import router as subber_settings_router
from mediamop.modules.subber.subber_webhook_api import router as subber_webhook_router

router = APIRouter(prefix="/subber", tags=["subber"])
router.include_router(subber_webhook_router)
router.include_router(subber_settings_router)
router.include_router(subber_library_router)
router.include_router(subber_jobs_inspection_router)
