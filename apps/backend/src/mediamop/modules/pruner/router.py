"""Pruner HTTP routes — product APIs mount here when job families ship (Phase 2+)."""

from __future__ import annotations

from fastapi import APIRouter

from mediamop.modules.pruner.pruner_instances_api import router as pruner_instances_router
from mediamop.modules.pruner.pruner_jobs_inspection_api import router as pruner_jobs_inspection_router
from mediamop.modules.pruner.pruner_overview_stats_api import router as pruner_overview_stats_router

router = APIRouter(tags=["pruner"])
router.include_router(pruner_overview_stats_router)
router.include_router(pruner_jobs_inspection_router)
router.include_router(pruner_instances_router)
