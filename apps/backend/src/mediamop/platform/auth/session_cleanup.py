"""Periodic cleanup for server-side auth sessions."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.platform.auth.service import cleanup_inactive_sessions

logger = logging.getLogger(__name__)
_INTERVAL_SECONDS = 3600


async def _session_cleanup_loop(
    session_factory: sessionmaker[Session],
    *,
    stop_event: asyncio.Event,
    settings: MediaMopSettings,
    interval_seconds: float = _INTERVAL_SECONDS,
) -> None:
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            pass
        if stop_event.is_set():
            break
        try:
            with session_factory() as session:
                removed = cleanup_inactive_sessions(session, settings=settings)
                session.commit()
            if removed:
                logger.info("auth event: cleaned up inactive sessions (count=%s)", removed)
            else:
                logger.debug("auth event: inactive session cleanup found nothing to remove")
        except Exception:
            logger.exception("auth event: inactive session cleanup failed")


def start_session_cleanup_task(
    session_factory: sessionmaker[Session],
    *,
    stop_event: asyncio.Event,
    settings: MediaMopSettings,
) -> asyncio.Task:
    return asyncio.create_task(
        _session_cleanup_loop(session_factory, stop_event=stop_event, settings=settings),
        name="auth-session-cleanup",
    )


async def stop_session_cleanup_task(task: asyncio.Task) -> None:
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
