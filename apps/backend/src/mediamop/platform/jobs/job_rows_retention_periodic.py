"""Periodic pruning of terminal job rows from all three module queues.

Deletes completed/failed/cancelled/handler_ok_finalize_failed rows whose ``updated_at``
is older than ``job_rows_retention_days`` (default 7). Runs on the global asyncio event
loop — one background task, shared across all three job tables.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.pruner.pruner_jobs_model import PrunerJob, PrunerJobStatus
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.modules.subber.subber_jobs_model import SubberJob, SubberJobStatus

logger = logging.getLogger(__name__)

_TERMINAL_REFINER = (
    RefinerJobStatus.COMPLETED.value,
    RefinerJobStatus.FAILED.value,
    RefinerJobStatus.HANDLER_OK_FINALIZE_FAILED.value,
    RefinerJobStatus.CANCELLED.value,
)
_TERMINAL_PRUNER = (
    PrunerJobStatus.COMPLETED.value,
    PrunerJobStatus.FAILED.value,
    PrunerJobStatus.HANDLER_OK_FINALIZE_FAILED.value,
)
_TERMINAL_SUBBER = (
    SubberJobStatus.COMPLETED.value,
    SubberJobStatus.FAILED.value,
    SubberJobStatus.HANDLER_OK_FINALIZE_FAILED.value,
)


def prune_job_rows(session: Session, *, cutoff: datetime) -> dict[str, int]:
    refiner_del = session.execute(
        delete(RefinerJob).where(
            RefinerJob.status.in_(_TERMINAL_REFINER),
            RefinerJob.updated_at < cutoff,
        )
    )
    pruner_del = session.execute(
        delete(PrunerJob).where(
            PrunerJob.status.in_(_TERMINAL_PRUNER),
            PrunerJob.updated_at < cutoff,
        )
    )
    subber_del = session.execute(
        delete(SubberJob).where(
            SubberJob.status.in_(_TERMINAL_SUBBER),
            SubberJob.updated_at < cutoff,
        )
    )
    return {
        "refiner": refiner_del.rowcount,
        "pruner": pruner_del.rowcount,
        "subber": subber_del.rowcount,
    }


def _run_prune_tick(session_factory: sessionmaker[Session], *, settings: MediaMopSettings) -> dict[str, int]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.job_rows_retention_days)
    with session_factory() as session:
        with session.begin():
            counts = prune_job_rows(session, cutoff=cutoff)
    return counts


async def _run_job_rows_retention_forever(
    session_factory: sessionmaker[Session],
    settings: MediaMopSettings,
    *,
    stop_event: asyncio.Event,
) -> None:
    loop = asyncio.get_running_loop()
    interval = float(settings.job_rows_retention_schedule_interval_seconds)
    while not stop_event.is_set():
        try:
            counts = await asyncio.to_thread(_run_prune_tick, session_factory, settings=settings)
            total = sum(counts.values())
            if total:
                logger.info(
                    "Job-row retention pruned terminal rows refiner=%d pruner=%d subber=%d",
                    counts["refiner"],
                    counts["pruner"],
                    counts["subber"],
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Job-row retention prune tick failed")
        deadline = loop.time() + interval
        while loop.time() < deadline and not stop_event.is_set():
            await asyncio.sleep(min(1.0, deadline - loop.time()))


def start_job_rows_retention_tasks(
    session_factory: sessionmaker[Session],
    *,
    stop_event: asyncio.Event,
    settings: MediaMopSettings,
) -> list[asyncio.Task[None]]:
    return [
        asyncio.create_task(
            _run_job_rows_retention_forever(session_factory, settings, stop_event=stop_event),
            name="platform-job-rows-retention",
        )
    ]


async def stop_job_rows_retention_tasks(tasks: list[asyncio.Task[None]]) -> None:
    for task in tasks:
        if not task.done():
            task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
