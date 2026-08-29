"""Refiner HTTP: what acceleration this machine offers — ``/api/v1/refiner/hardware``.

Read-only and deliberately honest about what it is reporting: **methods this ffmpeg build
was compiled with**, not devices proven to work. An operator should see what is on offer
before choosing, and offering a choice that cannot work is worse than offering fewer.

The Windows tray package ships its own ffmpeg build, so this genuinely differs by install
and cannot be answered from documentation.
"""

from __future__ import annotations

from fastapi import APIRouter

from mediamop.api.deps import SettingsDep
from mediamop.modules.refiner.refiner_hardware_acceleration import (
    STRICTNESS_LEVELS,
    VENDOR_METHODS,
    detect_acceleration,
)
from mediamop.modules.refiner.refiner_remux_mux import resolve_ffprobe_ffmpeg
from mediamop.modules.refiner.schemas_refiner_hardware import RefinerHardwareOut
from mediamop.platform.auth.deps_auth import UserPublicDep

router = APIRouter(tags=["refiner"])


@router.get("/refiner/hardware", response_model=RefinerHardwareOut)
def get_refiner_hardware(_user: UserPublicDep, settings: SettingsDep) -> RefinerHardwareOut:
    """What ffmpeg on this machine reports it can do."""

    try:
        _, ffmpeg_bin = resolve_ffprobe_ffmpeg(mediamop_home=settings.mediamop_home)
    except RuntimeError as exc:
        # A source install without ffmpeg on PATH is a supported state — Refiner reports
        # it elsewhere and refuses passes with a clear reason. Reporting "no acceleration"
        # here is the honest answer; letting the endpoint 500 would make a missing
        # optional tool look like a broken application.
        return RefinerHardwareOut(
            detected=False,
            available_methods=[],
            vendors=[],
            selectable_vendors=sorted(VENDOR_METHODS),
            strictness_levels=list(STRICTNESS_LEVELS),
            detail=f"MediaMop could not find ffmpeg, so it cannot report acceleration methods. {exc}",
        )
    report = detect_acceleration(ffmpeg_bin)
    return RefinerHardwareOut(
        detected=report.detected,
        available_methods=list(report.available_methods),
        vendors=list(report.vendors),
        selectable_vendors=sorted(VENDOR_METHODS),
        strictness_levels=list(STRICTNESS_LEVELS),
        detail=report.detail,
    )
