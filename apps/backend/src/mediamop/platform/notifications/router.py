"""Notification channels API — operators only."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Request
from starlette import status

from mediamop.api.deps import DbSessionDep, SettingsDep
from mediamop.platform.auth.authorization import RequireOperatorDep
from mediamop.platform.auth.csrf import (
    current_raw_session_token,
    require_session_secret,
    validate_browser_post_origin,
    verify_csrf_token,
)
from mediamop.platform.notifications.dispatch import test_dispatch_notification_channel
from mediamop.platform.notifications.model import NotificationChannel
from mediamop.platform.notifications.ops import (
    create_notification_channel,
    delete_notification_channel,
    get_notification_channel,
    list_notification_channels,
    update_notification_channel,
)
from mediamop.platform.notifications.schemas import (
    NotificationChannelIn,
    NotificationChannelListOut,
    NotificationChannelOut,
    NotificationChannelTestIn,
    NotificationChannelTestOut,
)

router = APIRouter(tags=["notifications"])
logger = logging.getLogger(__name__)


def _channel_out(row: NotificationChannel) -> NotificationChannelOut:
    return NotificationChannelOut(
        id=row.id,
        label=row.label,
        provider=row.provider,
        url=row.url,
        events=_parse_events_safe(row.events_json),
        enabled=row.enabled,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _parse_events_safe(events_json: str) -> list[str]:
    try:
        return [e for e in json.loads(events_json) if isinstance(e, str)]
    except (ValueError, TypeError):
        return []


@router.get("/suite/notification-channels", response_model=NotificationChannelListOut)
def get_notification_channels(_user: RequireOperatorDep, db: DbSessionDep) -> NotificationChannelListOut:
    rows = list_notification_channels(db)
    return NotificationChannelListOut(items=[_channel_out(r) for r in rows])


@router.post("/suite/notification-channels", response_model=NotificationChannelOut, status_code=status.HTTP_201_CREATED)
def post_notification_channel(
    body: NotificationChannelIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> NotificationChannelOut:
    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token, raw_session_token=current_raw_session_token(request, settings)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Your confirmation token expired. Refresh the page and try again.")
    try:
        row = create_notification_channel(
            db,
            label=body.label,
            provider=body.provider,
            url=body.url,
            events=body.events,
            enabled=body.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return _channel_out(row)


@router.put("/suite/notification-channels/{channel_id}", response_model=NotificationChannelOut)
def put_notification_channel(
    channel_id: int,
    body: NotificationChannelIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> NotificationChannelOut:
    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token, raw_session_token=current_raw_session_token(request, settings)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Your confirmation token expired. Refresh the page and try again.")
    try:
        row = update_notification_channel(
            db,
            channel_id,
            label=body.label,
            provider=body.provider,
            url=body.url,
            events=body.events,
            enabled=body.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification channel not found.")
    db.commit()
    return _channel_out(row)


@router.delete("/suite/notification-channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_notification_channel_route(
    channel_id: int,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> None:
    validate_browser_post_origin(request, settings)
    result = delete_notification_channel(db, channel_id)
    if result == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification channel not found.")
    db.commit()


@router.post("/suite/notification-channels/{channel_id}/test", response_model=NotificationChannelTestOut)
def post_notification_channel_test(
    channel_id: int,
    body: NotificationChannelTestIn,
    request: Request,
    _user: RequireOperatorDep,
    db: DbSessionDep,
    settings: SettingsDep,
) -> NotificationChannelTestOut:
    validate_browser_post_origin(request, settings)
    secret = require_session_secret(settings)
    if not verify_csrf_token(secret, body.csrf_token, raw_session_token=current_raw_session_token(request, settings)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Your confirmation token expired. Refresh the page and try again.")
    row = get_notification_channel(db, channel_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification channel not found.")
    error = test_dispatch_notification_channel(row)
    return NotificationChannelTestOut(ok=error is None, error=error)
