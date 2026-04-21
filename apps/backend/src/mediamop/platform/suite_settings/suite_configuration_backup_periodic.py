"""Periodic automatic suite configuration backup scheduler."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.platform.suite_settings.service import ensure_suite_settings_row
from mediamop.platform.suite_settings.suite_configuration_backup_service import create_suite_configuration_backup

logger = logging.getLogger(__name__)

SUITE_CONFIGURATION_BACKUP_FAILURE_COOLDOWN_SECONDS = 5.0


def run_suite_configuration_backup_tick(
    session_factory: sessionmaker[Session],
    *,
    settings: MediaMopSettings,
    now: datetime | None = None,
) -> int:
    when = now if now is not None else datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    with session_factory() as session:
        with session.begin():
            suite = ensure_suite_settings_row(session)
            if not bool(getattr(suite, "configuration_backup_enabled", False)):
                return 0
            hours = int(getattr(suite, "configuration_backup_interval_hours", 24) or 24)
            interval_seconds = max(3600, min(30 * 24 * 3600, hours * 3600))
            last = getattr(suite, "configuration_backup_last_run_at", None)
            if last is not None:
                last_at = last if last.tzinfo else last.replace(tzinfo=timezone.utc)
                if (when - last_at).total_seconds() < float(interval_seconds):
                    return 0
            create_suite_configuration_backup(session, settings=settings)
            suite.configuration_backup_last_run_at = when
            session.flush()
            return 1


async def _run_suite_configuration_backup_forever(
    session_factory: sessionmaker[Session],
    settings: MediaMopSettings,
    *,
    stop_event: asyncio.Event,
) -> None:
    loop = asyncio.get_running_loop()
    scan_iv = 60.0
    while not stop_event.is_set():
        def _once() -> int:
            return run_suite_configuration_backup_tick(session_factory, settings=settings)

        try:
            await asyncio.to_thread(_once)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Suite configuration backup tick failed")
            fail_deadline = loop.time() + SUITE_CONFIGURATION_BACKUP_FAILURE_COOLDOWN_SECONDS
            while loop.time() < fail_deadline and not stop_event.is_set():
                await asyncio.sleep(min(0.25, fail_deadline - loop.time()))
            continue
        if stop_event.is_set():
            break
        deadline = loop.time() + scan_iv
        while loop.time() < deadline and not stop_event.is_set():
            await asyncio.sleep(min(0.25, deadline - loop.time()))


def start_suite_configuration_backup_tasks(
    session_factory: sessionmaker[Session],
    *,
    stop_event: asyncio.Event,
    settings: MediaMopSettings,
) -> list[asyncio.Task[None]]:
    return [
        asyncio.create_task(
            _run_suite_configuration_backup_forever(session_factory, settings, stop_event=stop_event),
            name="suite-configuration-backup",
        )
    ]


async def stop_suite_configuration_backup_tasks(tasks: list[asyncio.Task[None]]) -> None:
    for t in tasks:
        if not t.done():
            t.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
