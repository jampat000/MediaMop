"""Subber HTTP routes — Subber-owned ``subber_jobs`` operator APIs only."""

from __future__ import annotations

from fastapi import APIRouter

from mediamop.modules.subber.subber_supplied_cue_timeline_constraints_check_api import (
    router as subber_supplied_cue_timeline_constraints_check_router,
)

router = APIRouter(tags=["subber"])
router.include_router(subber_supplied_cue_timeline_constraints_check_router)
