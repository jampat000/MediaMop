"""Authenticated dashboard routes."""

from __future__ import annotations

from fastapi import APIRouter

from mediamop.api.deps import SettingsDep
from mediamop.modules.dashboard.schemas import DashboardStatusOut
from mediamop.modules.dashboard.service import build_dashboard_status
from mediamop.platform.auth.deps_auth import UserPublicDep

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/status", response_model=DashboardStatusOut)
def get_dashboard_status(
    _user: UserPublicDep,
    settings: SettingsDep,
) -> DashboardStatusOut:
    """Read-only shell dashboard — system + optional Fetcher liveness probe."""

    return build_dashboard_status(settings)
