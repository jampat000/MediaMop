"""Refiner HTTP: read-only runtime settings (in-process ``refiner_jobs`` worker count)."""

from __future__ import annotations

from fastapi import APIRouter

from weir.api.deps import SettingsDep
from weir.platform.auth.authorization import RequireOperatorDep
from weir.refiner.refiner_runtime_visibility import refiner_runtime_settings_from_settings
from weir.refiner.schemas_refiner_runtime_visibility import RefinerRuntimeSettingsOut

router = APIRouter(tags=["refiner"])


@router.get(
    "/refiner/runtime-settings",
    response_model=RefinerRuntimeSettingsOut,
)
def get_refiner_runtime_settings(
    settings: SettingsDep,
    _user: RequireOperatorDep,
) -> RefinerRuntimeSettingsOut:
    """Refiner-only snapshot of configured in-process worker concurrency (env at process start)."""

    return refiner_runtime_settings_from_settings(settings)
