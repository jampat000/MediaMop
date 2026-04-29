"""Pruner-only in-process asyncio worker loop — claims ``pruner_jobs`` only."""

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
from mediamop.platform.http.request_context import job_logging_context
from mediamop.modules.queue_worker.job_kind_boundaries import (
    PRUNER_QUEUE_JOB_KIND_PREFIX,
    job_kind_forbidden_on_pruner_lane,
    validate_pruner_worker_handler_registry,
)
from mediamop.modules.pruner.pruner_jobs_ops import (
    claim_next_eligible_pruner_job,
    complete_claimed_pruner_job,
    fail_claimed_pruner_job,
    fail_leased_pruner_job_after_complete_failure,
)
from mediamop.platform.jobs.worker_health import worker_heartbeat, worker_started, worker_stopped
from mediamop.platform.observability.failure_messages import operator_failure_from_exception

logger = logging.getLogger(__name__)

DEFAULT_PRUNER_JOB_LEASE_SECONDS = 300
PRUNER_WORKER_IDLE_SLEEP_SECONDS = 5.0
PRUNER_WORKER_TICK_ERROR_BACKOFF_SECONDS = 1.0
PRUNER_TERMINALIZATION_FAILURE_PREFIX = "pruner_terminalization_failure: "


@dataclass(frozen=True, slots=True)
class PrunerJobWorkContext:
    """Immutable view passed to job handlers after a successful claim (outside the claim txn)."""

    id: int
    job_kind: str
    payload_json: str | None
    lease_owner: str


class PrunerNoHandlerForJobKind(LookupError):
    """Raised when ``job_kind`` has no registered handler."""

    def __init__(self, job_kind: str) -> None:
        self.job_kind = job_kind
        super().__init__(f"no Pruner job handler registered for job_kind={job_kind!r}")


def default_pruner_job_handler_registry() -> dict[str, Callable[[PrunerJobWorkContext], None]]:
    return {}


def process_one_pruner_job(
    session_factory: sessionmaker[Session],
    *,
    lease_owner: str,
    job_handlers: Mapping[str, Callable[[PrunerJobWorkContext], None]],
    lease_seconds: int = DEFAULT_PRUNER_JOB_LEASE_SECONDS,
    now: datetime | None = None,
) -> Literal["idle", "processed"]:
    when = now if now is not None else datetime.now(timezone.utc)
    lease_until = when + timedelta(seconds=lease_seconds)

    with session_factory() as session:
        with session.begin():
            job = claim_next_eligible_pruner_job(
                session,
                lease_owner=lease_owner,
                lease_expires_at=lease_until,
                now=when,
            )
            if job is None:
                return "idle"
            ctx = PrunerJobWorkContext(
                id=job.id,
                job_kind=job.job_kind,
                payload_json=job.payload_json,
                lease_owner=lease_owner,
            )

    if job_kind_forbidden_on_pruner_lane(ctx.job_kind):
        err_text = (
            "pruner worker refused job_kind reserved for another module lane: "
            f"{ctx.job_kind!r} (row id={ctx.id})"
        )[:10_000]
        try:
            with session_factory() as session:
                with session.begin():
                    fail_claimed_pruner_job(
                        session,
                        job_id=ctx.id,
                        lease_owner=ctx.lease_owner,
                        error_message=err_text,
                        now=when,
                    )
        except Exception:
            logger.exception("Pruner fail_claimed after cross-lane guard job_id=%s", ctx.id)
        return "processed"

    if not ctx.job_kind.startswith(PRUNER_QUEUE_JOB_KIND_PREFIX):
        err_text = (
            "pruner worker refused job_kind missing required pruner.* prefix: "
            f"{ctx.job_kind!r} (row id={ctx.id})"
        )[:10_000]
        try:
            with session_factory() as session:
                with session.begin():
                    fail_claimed_pruner_job(
                        session,
                        job_id=ctx.id,
                        lease_owner=ctx.lease_owner,
                        error_message=err_text,
                        now=when,
                    )
        except Exception:
            logger.exception("Pruner fail_claimed after pruner.* prefix guard job_id=%s", ctx.id)
        return "processed"

    handler = job_handlers.get(ctx.job_kind)
    if handler is None:
        exc: BaseException = PrunerNoHandlerForJobKind(ctx.job_kind)
        err_text = str(exc)[:10_000]
        try:
            with session_factory() as session:
                with session.begin():
                    fail_claimed_pruner_job(
                        session,
                        job_id=ctx.id,
                        lease_owner=ctx.lease_owner,
                        error_message=err_text,
                        now=when,
                    )
        except Exception:
            logger.exception("Pruner fail_claimed after missing handler job_id=%s", ctx.id)
        return "processed"

    try:
        with job_logging_context(ctx.id):
            handler(ctx)
    except Exception as exc:
        logger.exception("Pruner job handler failed for job_id=%s kind=%s", ctx.id, ctx.job_kind)
        err_text = operator_failure_from_exception(
            module="Pruner",
            action="job",
            exc=exc,
            recoverable=False,
        ).message[:10_000]
        try:
            with session_factory() as session:
                with session.begin():
                    fail_claimed_pruner_job(
                        session,
                        job_id=ctx.id,
                        lease_owner=ctx.lease_owner,
                        error_message=err_text,
                        now=when,
                    )
        except Exception:
            logger.exception("Pruner fail_claimed_pruner_job failed after handler error job_id=%s", ctx.id)
        return "processed"

    complete_ok = True
    complete_err: str | None = None
    try:
        with session_factory() as session:
            with session.begin():
                ok = complete_claimed_pruner_job(
                    session,
                    job_id=ctx.id,
                    lease_owner=ctx.lease_owner,
                    now=when,
                )
                if not ok:
                    complete_ok = False
                    complete_err = "complete_claimed_pruner_job refused (lease/state mismatch)"
    except Exception as exc:
        complete_ok = False
        logger.exception("Pruner complete_claimed_pruner_job failed job_id=%s", ctx.id)
        complete_err = str(exc)

    if not complete_ok and complete_err is not None:
        bounded = (PRUNER_TERMINALIZATION_FAILURE_PREFIX + complete_err)[:10_000]
        try:
            with session_factory() as session:
                with session.begin():
                    recovered = fail_leased_pruner_job_after_complete_failure(
                        session,
                        job_id=ctx.id,
                        lease_owner=ctx.lease_owner,
                        error_message=bounded,
                        now=when,
                    )
            if not recovered:
                logger.warning(
                    "Pruner terminalization recovery did not apply job_id=%s owner=%s",
                    ctx.id,
                    ctx.lease_owner,
                )
        except Exception:
            logger.exception(
                "Pruner fail_leased_pruner_job_after_complete_failure failed job_id=%s",
                ctx.id,
            )
    return "processed"


def _lease_owner(worker_index: int) -> str:
    return f"{socket.gethostname()}-{os.getpid()}-pruner-w{worker_index}"


async def pruner_worker_run_forever(
    session_factory: sessionmaker[Session],
    *,
    worker_index: int,
    stop_event: asyncio.Event,
    job_handlers: Mapping[str, Callable[[PrunerJobWorkContext], None]] | None = None,
    idle_sleep_seconds: float = PRUNER_WORKER_IDLE_SLEEP_SECONDS,
    lease_seconds: int = DEFAULT_PRUNER_JOB_LEASE_SECONDS,
) -> None:
    owner = _lease_owner(worker_index)
    handlers = job_handlers if job_handlers is not None else default_pruner_job_handler_registry()
    worker_started("pruner", worker_index)
    try:
        while not stop_event.is_set():
            worker_heartbeat("pruner", worker_index)

            def _tick() -> Literal["idle", "processed"]:
                return process_one_pruner_job(
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
                logger.exception("Pruner worker tick crashed worker_index=%s", worker_index)
                await asyncio.sleep(PRUNER_WORKER_TICK_ERROR_BACKOFF_SECONDS)
                continue

            if stop_event.is_set():
                break

            if outcome == "idle":
                loop = asyncio.get_running_loop()
                deadline = loop.time() + idle_sleep_seconds
                while loop.time() < deadline and not stop_event.is_set():
                    worker_heartbeat("pruner", worker_index)
                    remaining = deadline - loop.time()
                    if remaining <= 0:
                        break
                    await asyncio.sleep(min(0.25, remaining))
    finally:
        worker_stopped("pruner", worker_index)


def start_pruner_worker_background_tasks(
    session_factory: sessionmaker[Session],
    settings: MediaMopSettings,
    *,
    job_handlers: Mapping[str, Callable[[PrunerJobWorkContext], None]] | None = None,
    stop_event: asyncio.Event | None = None,
) -> tuple[asyncio.Event, list[asyncio.Task[None]]]:
    if settings.pruner_worker_count > 1:
        logger.warning(
            "Pruner pruner_worker_count=%s: multi-worker is guarded under SQLite single-writer.",
            settings.pruner_worker_count,
        )

    handlers: Mapping[str, Callable[[PrunerJobWorkContext], None]]
    if job_handlers is not None:
        handlers = job_handlers
    elif settings.pruner_worker_count == 0:
        handlers = {}
    else:
        msg = "job_handlers is required when pruner_worker_count > 0"
        raise TypeError(msg)

    validate_pruner_worker_handler_registry(handlers)

    stop = stop_event if stop_event is not None else asyncio.Event()
    tasks: list[asyncio.Task[None]] = []
    for i in range(settings.pruner_worker_count):
        t = asyncio.create_task(
            pruner_worker_run_forever(
                session_factory,
                worker_index=i,
                stop_event=stop,
                job_handlers=handlers,
            ),
            name=f"pruner-worker-{i}",
        )
        tasks.append(t)
    return stop, tasks


async def stop_pruner_worker_background_tasks(
    stop: asyncio.Event,
    tasks: list[asyncio.Task[None]],
) -> None:
    stop.set()
    for t in tasks:
        if not t.done():
            t.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
