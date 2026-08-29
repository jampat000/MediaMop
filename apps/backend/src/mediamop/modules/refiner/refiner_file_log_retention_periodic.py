"""Periodic pruning of the per-file processing record.

Separate from the suite's log retention on purpose. A suite log is for diagnosing the
application and a per-file record is for diagnosing a *file*, and somebody may only ask
about a file long after the fact — so the two need different lifetimes, and one setting
could not give them that.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.refiner_file_log_service import prune_file_logs
from mediamop.modules.refiner.refiner_operator_settings_service import ensure_refiner_operator_settings_row

logger = logging.getLogger(__name__)

#: Records are pruned by age, so checking often buys nothing. Hourly keeps the window
#: honest without a sweep that runs more than the thing it is sweeping.
PRUNE_INTERVAL_SECONDS = 3600.0


def prune_once(session_factory: sessionmaker[Session]) -> int:
    """One pruning pass. Returns how many records were removed."""

    with session_factory() as session, session.begin():
        operator = ensure_refiner_operator_settings_row(session)
        days = int(operator.file_log_retention_days)
        # 0 means keep forever, matching the setting's own wording. Reading it the other
        # way would silently destroy the history the feature exists to keep, which is the
        # worst possible direction for that ambiguity.
        if days <= 0:
            return 0
        return prune_file_logs(session, retention_days=days)


async def _run_forever(session_factory: sessionmaker[Session], *, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            removed = await asyncio.to_thread(prune_once, session_factory)
            if removed:
                logger.info("Refiner removed %s processing record(s) past their retention window.", removed)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Retention failing must not take the task down: the next tick tries again,
            # and a stopped pruner is a database that grows silently.
            logger.exception("Refiner processing-record retention failed.")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=PRUNE_INTERVAL_SECONDS)


def start_refiner_file_log_retention_tasks(
    session_factory: sessionmaker[Session],
    *,
    stop_event: asyncio.Event,
    settings: MediaMopSettings,
) -> list[asyncio.Task[None]]:
    return [
        asyncio.create_task(
            _run_forever(session_factory, stop_event=stop_event),
            name="refiner-file-log-retention",
        )
    ]


async def stop_refiner_file_log_retention_tasks(tasks: list[asyncio.Task[None]]) -> None:
    for task in tasks:
        if not task.done():
            task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
