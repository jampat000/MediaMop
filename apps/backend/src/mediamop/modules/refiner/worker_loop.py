"""Refiner-only in-process worker loop (Pass 14–15).

Claims rows from ``refiner_jobs``, dispatches by ``job_kind``, then completes or fails via
:class:`mediamop.modules.refiner.jobs_ops`. Production handlers are built from
:class:`~mediamop.core.config.MediaMopSettings` (Pass 15–15.5: Radarr + Sonarr live cleanup drives).
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.refiner.jobs_ops import (
    claim_next_eligible_refiner_job,
    complete_claimed_refiner_job,
    fail_claimed_refiner_job,
)

logger = logging.getLogger(__name__)

DEFAULT_REFINER_JOB_LEASE_SECONDS = 300
REFINER_WORKER_IDLE_SLEEP_SECONDS = 5.0
REFINER_WORKER_TICK_ERROR_BACKOFF_SECONDS = 1.0


@dataclass(frozen=True, slots=True)
class RefinerJobWorkContext:
    """Immutable view passed to job handlers after a successful claim (outside the claim txn)."""

    id: int
    job_kind: str
    payload_json: str | None
    lease_owner: str


class RefinerNoHandlerForJobKind(LookupError):
    """Raised when ``job_kind`` has no registered handler (becomes ``fail_claimed`` path)."""

    def __init__(self, job_kind: str) -> None:
        self.job_kind = job_kind
        super().__init__(f"no Refiner job handler registered for job_kind={job_kind!r}")


def default_refiner_job_handler_registry() -> dict[str, Callable[[RefinerJobWorkContext], None]]:
    """Empty registry for tests or callers that inject handlers explicitly."""

    return {}


def process_one_refiner_job(
    session_factory: sessionmaker[Session],
    *,
    lease_owner: str,
    job_handlers: Mapping[str, Callable[[RefinerJobWorkContext], None]],
    lease_seconds: int = DEFAULT_REFINER_JOB_LEASE_SECONDS,
    now: datetime | None = None,
) -> Literal["idle", "processed"]:
    """Claim at most one job, run handler, then complete or fail via :mod:`jobs_ops`.

    Returns ``\"idle\"`` when no row was claimable; ``\"processed\"`` when a row was leased and
    finished (success or handler failure).
    """

    when = now if now is not None else datetime.now(timezone.utc)
    lease_until = when + timedelta(seconds=lease_seconds)

    with session_factory() as session:
        with session.begin():
            job = claim_next_eligible_refiner_job(
                session,
                lease_owner=lease_owner,
                lease_expires_at=lease_until,
                now=when,
            )
            if job is None:
                return "idle"
            ctx = RefinerJobWorkContext(
                id=job.id,
                job_kind=job.job_kind,
                payload_json=job.payload_json,
                lease_owner=lease_owner,
            )

    handler = job_handlers.get(ctx.job_kind)
    if handler is None:
        exc: BaseException = RefinerNoHandlerForJobKind(ctx.job_kind)
        err_text = str(exc)[:10_000]
        try:
            with session_factory() as session:
                with session.begin():
                    fail_claimed_refiner_job(
                        session,
                        job_id=ctx.id,
                        lease_owner=ctx.lease_owner,
                        error_message=err_text,
                    )
        except Exception:
            logger.exception(
                "Refiner fail_claimed_refiner_job failed after missing handler job_id=%s",
                ctx.id,
            )
        return "processed"

    try:
        handler(ctx)
    except Exception as exc:
        logger.exception("Refiner job handler failed for job_id=%s kind=%s", ctx.id, ctx.job_kind)
        err_text = str(exc)[:10_000]
        try:
            with session_factory() as session:
                with session.begin():
                    fail_claimed_refiner_job(
                        session,
                        job_id=ctx.id,
                        lease_owner=ctx.lease_owner,
                        error_message=err_text,
                    )
        except Exception:
            logger.exception(
                "Refiner fail_claimed_refiner_job failed after handler error job_id=%s",
                ctx.id,
            )
        return "processed"

    try:
        with session_factory() as session:
            with session.begin():
                ok = complete_claimed_refiner_job(
                    session,
                    job_id=ctx.id,
                    lease_owner=ctx.lease_owner,
                )
                if not ok:
                    logger.warning(
                        "complete_claimed_refiner_job refused job_id=%s owner=%s (lease or state)",
                        ctx.id,
                        ctx.lease_owner,
                    )
    except Exception:
        logger.exception("Refiner complete_claimed_refiner_job failed job_id=%s", ctx.id)
    return "processed"


def _lease_owner(worker_index: int) -> str:
    return f"{socket.gethostname()}-{os.getpid()}-w{worker_index}"


async def refiner_worker_run_forever(
    session_factory: sessionmaker[Session],
    *,
    worker_index: int,
    stop_event: asyncio.Event,
    job_handlers: Mapping[str, Callable[[RefinerJobWorkContext], None]] | None = None,
    idle_sleep_seconds: float = REFINER_WORKER_IDLE_SLEEP_SECONDS,
    lease_seconds: int = DEFAULT_REFINER_JOB_LEASE_SECONDS,
) -> None:
    """One asyncio task: repeatedly process jobs until ``stop_event`` is set."""

    owner = _lease_owner(worker_index)
    handlers = job_handlers if job_handlers is not None else default_refiner_job_handler_registry()
    while not stop_event.is_set():

        def _tick() -> Literal["idle", "processed"]:
            return process_one_refiner_job(
                session_factory,
                lease_owner=owner,
                job_handlers=handlers,
                lease_seconds=lease_seconds,
            )

        try:
            outcome = await asyncio.to_thread(_tick)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Refiner worker tick crashed worker_index=%s", worker_index)
            await asyncio.sleep(REFINER_WORKER_TICK_ERROR_BACKOFF_SECONDS)
            continue

        if stop_event.is_set():
            break

        if outcome == "idle":
            loop = asyncio.get_running_loop()
            deadline = loop.time() + idle_sleep_seconds
            while loop.time() < deadline and not stop_event.is_set():
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                await asyncio.sleep(min(0.25, remaining))
        # processed: tight spin for back-to-back queue drain


def start_refiner_worker_background_tasks(
    session_factory: sessionmaker[Session],
    settings: MediaMopSettings,
    *,
    job_handlers: Mapping[str, Callable[[RefinerJobWorkContext], None]] | None = None,
    stop_event: asyncio.Event | None = None,
) -> tuple[asyncio.Event, list[asyncio.Task[None]]]:
    """Create one asyncio task per configured Refiner worker (count clamped at load time)."""

    handlers: Mapping[str, Callable[[RefinerJobWorkContext], None]]
    if job_handlers is not None:
        handlers = job_handlers
    else:
        from mediamop.modules.refiner.job_handlers_registry import build_production_refiner_job_handlers

        handlers = build_production_refiner_job_handlers(settings)

    stop = stop_event if stop_event is not None else asyncio.Event()
    tasks: list[asyncio.Task[None]] = []
    for i in range(settings.refiner_worker_count):
        t = asyncio.create_task(
            refiner_worker_run_forever(
                session_factory,
                worker_index=i,
                stop_event=stop,
                job_handlers=handlers,
            ),
            name=f"refiner-worker-{i}",
        )
        tasks.append(t)
    return stop, tasks


async def stop_refiner_worker_background_tasks(
    stop: asyncio.Event,
    tasks: list[asyncio.Task[None]],
) -> None:
    stop.set()
    for t in tasks:
        if not t.done():
            t.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
