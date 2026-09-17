"""Pause and resume processing — ``/api/v1/pause``.

This is the one pause switch. It is deliberately small: paused or not, an optional
expiry, and whether detection keeps running.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request
from starlette import status as http_status

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
from weir.platform.pause.schemas import PauseIn, PauseOut
from weir.platform.suite_settings.service import ensure_suite_settings_row
from weir.refiner.refiner_work_admission import resolve_pause_state

router = APIRouter(tags=["pause"])


def _verify_csrf(request: Request, settings: WeirSettings, token: str) -> None:
    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, token, raw_session_token=current_raw_session_token(request, settings)):
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Invalid or expired CSRF token.")


def _out(db: DbSessionDep) -> PauseOut:
    row = ensure_suite_settings_row(db)
    state = resolve_pause_state(row)
    if state.expired:
        # The pause lapsed while nothing was looking. Clear the stored flag so the screen
        # and the database agree, rather than reporting "not paused" over a row that
        # still says otherwise.
        row.processing_paused = False
        row.processing_paused_until = None
        db.flush()
    return PauseOut(
        paused=state.paused,
        paused_until=state.paused_until if state.paused else None,
        scan_while_paused=state.scan_while_paused,
        reason=state.reason,
        # Said plainly because the alternative reading — that a pause stops work dead —
        # is the one an operator will otherwise assume and be surprised by.
        in_flight_policy=("Work already running finishes. Pausing stops Weir starting anything new."),
    )


@router.get("/pause", response_model=PauseOut)
def get_pause(_user: UserPublicDep, db: DbSessionDep) -> PauseOut:
    return _out(db)


@router.put("/pause", response_model=PauseOut)
def put_pause(
    request: Request,
    _operator: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
    body: PauseIn,
) -> PauseOut:
    _verify_csrf(request, settings, body.csrf_token)
    row = ensure_suite_settings_row(db)
    row.processing_paused = bool(body.paused)
    row.scan_while_paused = bool(body.scan_while_paused)
    if not body.paused:
        row.processing_paused_until = None
    elif body.pause_for_minutes is not None:
        row.processing_paused_until = datetime.now(UTC) + timedelta(minutes=int(body.pause_for_minutes))
    else:
        # An indefinite pause is a deliberate choice, so it clears any previous expiry
        # rather than inheriting one the operator did not ask for again.
        row.processing_paused_until = None
    db.flush()
    return _out(db)
