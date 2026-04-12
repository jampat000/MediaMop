"""Refiner HTTP routes (reserved for Refiner-native surfaces).

Radarr/Sonarr download-queue failed-import cleanup and related Fetcher operator APIs live under
``mediamop.modules.fetcher`` (e.g. ``failed_imports_api`` for policy/runtime/drives, ``fetcher_jobs_api`` for persisted
``fetcher_jobs`` inspection and manual finalize recovery, ``fetcher_arr_search_api`` for manual Arr search enqueue).
"""

from __future__ import annotations

from fastapi import APIRouter

from mediamop.modules.refiner.refiner_candidate_gate_api import router as refiner_candidate_gate_router
from mediamop.modules.refiner.refiner_file_remux_pass_api import router as refiner_file_remux_pass_router
from mediamop.modules.refiner.refiner_supplied_payload_evaluation_api import (
    router as refiner_supplied_payload_evaluation_router,
)

router = APIRouter(tags=["refiner"])
router.include_router(refiner_supplied_payload_evaluation_router)
router.include_router(refiner_candidate_gate_router)
router.include_router(refiner_file_remux_pass_router)
