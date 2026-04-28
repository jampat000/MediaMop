"""Periodic runtime pruning for MediaMop log retention."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.platform.suite_settings.logs_service import prune_logs_for_retention

logger = logging.getLogger(__name__)

LOG_RETENTION_SCAN_INTERVAL_SECONDS = 3600.0
LOG_RETENTION_MIN_RUN_INTERVAL_SECONDS = 24 * 3600.0

_last_prune_at: datetime | None = None


def reset_log_retention_periodic_state_for_tests() -> None:
    global _last_prune_at
    _last_prune_at = None


def run_log_retention_tick(
    session_factory: sessionmaker[Session],
    *,
    settings: MediaMopSettings,
    now: datetime | None = None,
) -> int:
    global _last_prune_at
    when = now if now is not None else datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    if _last_prune_at is not None and (when - _last_prune_at).total_seconds() < LOG_RETENTION_MIN_RUN_INTERVAL_SECONDS:
        return 0
    with session_factory() as session:
        with session.begin():
            prune_logs_for_retention(session, settings)
    _last_prune_at = when
    return 1


async def _run_log_retention_forever(
    session_factory: sessionmaker[Session],
    settings: MediaMopSettings,
    *,
    stop_event: asyncio.Event,
) -> None:
    loop = asyncio.get_running_loop()
    while not stop_event.is_set():
        try:
            await asyncio.to_thread(run_log_retention_tick, session_factory, settings=settings)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Log retention tick failed")
        deadline = loop.time() + LOG_RETENTION_SCAN_INTERVAL_SECONDS
        while loop.time() < deadline and not stop_event.is_set():
            await asyncio.sleep(min(0.25, deadline - loop.time()))


def start_log_retention_tasks(
    session_factory: sessionmaker[Session],
    *,
    stop_event: asyncio.Event,
    settings: MediaMopSettings,
) -> list[asyncio.Task[None]]:
    return [
        asyncio.create_task(
            _run_log_retention_forever(session_factory, settings, stop_event=stop_event),
            name="suite-log-retention",
        )
    ]


async def stop_log_retention_tasks(tasks: list[asyncio.Task[None]]) -> None:
    for task in tasks:
        if not task.done():
            task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
