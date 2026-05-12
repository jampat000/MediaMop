"""Fire-and-forget outbound notification dispatch.

Each dispatch opens its own DB session, reads matching channels, then fires HTTP POSTs in a
daemon thread. The thread is not joined — callers do not wait.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

from mediamop.platform.notifications.model import NotificationChannel
from mediamop.platform.notifications.ops import get_channels_for_event

logger = logging.getLogger(__name__)

_DISPATCH_TIMEOUT_SECONDS = 10


def _build_webhook_payload(
    *,
    event: str,
    module: str,
    job_id: int,
    job_kind: str,
    title: str,
    detail: str,
) -> bytes:
    return json.dumps(
        {
            "event": event,
            "module": module,
            "job_id": job_id,
            "job_kind": job_kind,
            "title": title,
            "detail": detail,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "app": "MediaMop",
        }
    ).encode()


def _build_discord_payload(*, title: str, detail: str, event: str, module: str, job_id: int) -> bytes:
    color = 0x2ECC71 if "completed" in event else 0xE74C3C
    return json.dumps(
        {
            "embeds": [
                {
                    "title": title,
                    "description": detail,
                    "color": color,
                    "fields": [
                        {"name": "Module", "value": module, "inline": True},
                        {"name": "Job ID", "value": str(job_id), "inline": True},
                    ],
                    "footer": {"text": "MediaMop"},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ]
        }
    ).encode()


def _post_one(channel: NotificationChannel, *, title: str, detail: str, event: str, module: str, job_id: int, job_kind: str) -> None:
    try:
        if channel.provider == "discord":
            body = _build_discord_payload(title=title, detail=detail, event=event, module=module, job_id=job_id)
        else:
            body = _build_webhook_payload(event=event, module=module, job_id=job_id, job_kind=job_kind, title=title, detail=detail)
        req = urllib.request.Request(
            channel.url,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "MediaMop/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=_DISPATCH_TIMEOUT_SECONDS) as resp:
            status = resp.status
        if status >= 400:
            logger.warning(
                "Notification channel %s (%s) returned HTTP %s for event=%s",
                channel.id,
                channel.label,
                status,
                event,
            )
    except Exception:
        logger.warning(
            "Notification dispatch failed for channel %s (%s) event=%s",
            channel.id,
            channel.label,
            event,
            exc_info=True,
        )


def _is_permanently_failed(session: "Session", module: str, job_id: int) -> bool:
    """Return True only when the job row has status='failed' (exhausted retries)."""
    from sqlalchemy import text  # local import avoids circular at module level

    safe_module = module if module in {"refiner", "pruner", "subber"} else None
    if safe_module is None:
        return True  # unknown module — let dispatch proceed
    try:
        row = session.execute(
            text(f"SELECT status FROM {safe_module}_jobs WHERE id = :id"),
            {"id": job_id},
        ).fetchone()
        return row is not None and row[0] == "failed"
    except Exception:
        return True  # on error, don't suppress the notification


def _dispatch_thread(
    session: "Session",
    *,
    event: str,
    module: str,
    job_id: int,
    job_kind: str,
    title: str,
    detail: str,
    verify_permanent: bool,
) -> None:
    try:
        if verify_permanent and not _is_permanently_failed(session, module, job_id):
            session.close()
            return

        channels = get_channels_for_event(session, event)
        # Also include channels subscribed to the generic (non-module-prefixed) event
        generic = event.removeprefix(f"{module}_")
        if generic != event:
            for ch in get_channels_for_event(session, generic):
                if ch not in channels:
                    channels.append(ch)
        session.close()
    except Exception:
        logger.warning("Notification dispatch: failed to read channels for event=%s", event, exc_info=True)
        try:
            session.close()
        except Exception:
            pass
        return

    for channel in channels:
        _post_one(channel, title=title, detail=detail, event=event, module=module, job_id=job_id, job_kind=job_kind)


def dispatch_job_notification(
    session_factory: "sessionmaker[Session]",
    *,
    module: str,
    event_kind: str,
    job_id: int,
    job_kind: str,
) -> None:
    """Schedule a daemon thread to send notifications for *event_kind* on *module*.

    ``event_kind`` should be ``"completed"`` or ``"failed"``.
    The per-module event (e.g. ``"refiner_job_completed"``) is fired, and matching channels are
    fetched and posted. Never raises — all errors are logged.
    """
    event = f"{module}_job_{event_kind}"
    if event_kind == "completed":
        title = f"{module.capitalize()} job completed"
        detail = f"Job {job_id} ({job_kind}) finished successfully."
    else:
        title = f"{module.capitalize()} job failed"
        detail = f"Job {job_id} ({job_kind}) exhausted all retry attempts."

    try:
        session = session_factory()
    except Exception:
        logger.warning("Notification dispatch: could not open session for event=%s", event, exc_info=True)
        return

    t = threading.Thread(
        target=_dispatch_thread,
        args=(session,),
        kwargs={
            "event": event,
            "module": module,
            "job_id": job_id,
            "job_kind": job_kind,
            "title": title,
            "detail": detail,
            "verify_permanent": (event_kind == "failed"),
        },
        daemon=True,
        name=f"mm-notify-{event}-{job_id}",
    )
    t.start()


def test_dispatch_notification_channel(
    channel: NotificationChannel,
    *,
    event: str = "job_completed",
    module: str = "refiner",
    job_id: int = 0,
    job_kind: str = "test",
) -> str | None:
    """Synchronously send one test notification. Returns error string or None on success."""
    try:
        _post_one(
            channel,
            title="MediaMop test notification",
            detail="This is a test notification from MediaMop.",
            event=event,
            module=module,
            job_id=job_id,
            job_kind=job_kind,
        )
        return None
    except Exception as exc:
        return str(exc)
