"""Refiner HTTP routes (Refiner-native surfaces).

Includes persisted-queue inspection via ``refiner_jobs_inspection_api`` (``GET …/refiner/jobs/inspection``).
"""

from __future__ import annotations

from fastapi import APIRouter

from mediamop.modules.refiner.refiner_candidate_gate_api import router as refiner_candidate_gate_router
from mediamop.modules.refiner.refiner_jobs_inspection_api import router as refiner_jobs_inspection_router
from mediamop.modules.refiner.file_remux_pass.api import router as refiner_file_remux_pass_router
from mediamop.modules.refiner.refiner_operator_settings_api import router as refiner_operator_settings_router
from mediamop.modules.refiner.refiner_path_settings_api import router as refiner_path_settings_router
from mediamop.modules.refiner.refiner_remux_rules_settings_api import router as refiner_remux_rules_settings_router
from mediamop.modules.refiner.refiner_runtime_settings_api import router as refiner_runtime_settings_router
from mediamop.modules.refiner.refiner_overview_stats_api import router as refiner_overview_stats_router
from mediamop.modules.refiner.refiner_supplied_payload_evaluation_api import (
    router as refiner_supplied_payload_evaluation_router,
)
from mediamop.modules.refiner.refiner_watched_folder_remux_scan_dispatch_api import (
    router as refiner_watched_folder_remux_scan_dispatch_router,
)

router = APIRouter(tags=["refiner"])
router.include_router(refiner_jobs_inspection_router)
router.include_router(refiner_operator_settings_router)
router.include_router(refiner_path_settings_router)
router.include_router(refiner_remux_rules_settings_router)
router.include_router(refiner_runtime_settings_router)
router.include_router(refiner_overview_stats_router)
router.include_router(refiner_supplied_payload_evaluation_router)
router.include_router(refiner_candidate_gate_router)
router.include_router(refiner_file_remux_pass_router)
router.include_router(refiner_watched_folder_remux_scan_dispatch_router)
