"""Trimmer HTTP routes — Trimmer-owned ``trimmer_jobs`` operator APIs only."""

from __future__ import annotations

from fastapi import APIRouter

from mediamop.modules.trimmer.trimmer_supplied_trim_plan_json_file_write_api import (
    router as trimmer_supplied_trim_plan_json_file_write_router,
)
from mediamop.modules.trimmer.trimmer_trim_plan_constraints_check_api import (
    router as trimmer_trim_plan_constraints_check_router,
)

router = APIRouter(tags=["trimmer"])
router.include_router(trimmer_trim_plan_constraints_check_router)
router.include_router(trimmer_supplied_trim_plan_json_file_write_router)
