"""Choosing the devices the Direct Play badge answers for (#467)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.orm import Session
from starlette import status

from weir.api.deps import DbSessionDep, SettingsDep
from weir.core.config import WeirSettings
from weir.platform.auth.authorization import RequireOperatorDep
from weir.platform.auth.csrf import (
    current_raw_session_token,
    require_session_secret,
    validate_browser_post_origin,
    verify_csrf_token,
)
from weir.platform.auth.deps_auth import UserPublicDep
from weir.refiner.direct_play import load_device_profiles
from weir.refiner.direct_play.service import (
    device_list_is_customised,
    save_selected_device_ids,
    selected_device_ids,
)
from weir.refiner.schemas_refiner_files import (
    DirectPlayDeviceOut,
    DirectPlayDevicesIn,
    DirectPlayDevicesOut,
)

router = APIRouter(tags=["refiner"])


def _out(db: Session, settings: WeirSettings) -> DirectPlayDevicesOut:
    chosen = set(selected_device_ids(db))
    return DirectPlayDevicesOut(
        devices=[
            DirectPlayDeviceOut(id=p.id, name=p.name, source=p.source, note=p.note, selected=p.id in chosen)
            for p in load_device_profiles(settings.weir_home)
        ],
        customised=device_list_is_customised(settings),
    )


@router.get("/refiner/direct-play/devices", response_model=DirectPlayDevicesOut)
def get_direct_play_devices(_user: UserPublicDep, db: DbSessionDep, settings: SettingsDep) -> DirectPlayDevicesOut:
    """The devices the badge can answer for, each with its source, and which ones you own."""

    return _out(db, settings)


@router.put("/refiner/direct-play/devices", response_model=DirectPlayDevicesOut)
def put_direct_play_devices(
    body: DirectPlayDevicesIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> DirectPlayDevicesOut:
    """Save which devices you own. Changes only the badge, never how a file is processed."""

    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token, raw_session_token=current_raw_session_token(request, settings)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired CSRF token.")
    save_selected_device_ids(db, settings, body.selected)
    db.commit()
    return _out(db, settings)
