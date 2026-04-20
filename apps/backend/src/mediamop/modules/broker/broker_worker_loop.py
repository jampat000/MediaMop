"""Broker-only in-process asyncio worker loop — claims ``broker_jobs`` only."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy.orm import Session, sessionmaker

from mediamop.core.config import MediaMopSettings
from mediamop.modules.broker.broker_jobs_ops import (
    claim_next_eligible_broker_job,
    complete_claimed_broker_job,
    fail_claimed_broker_job,
    fail_leased_broker_job_after_complete_failure,
)
from mediamop.modules.broker.broker_job_context import BrokerJobWorkContext
from mediamop.modules.queue_worker.job_kind_boundaries import (
    BROKER_QUEUE_JOB_KIND_PREFIX,
    job_kind_forbidden_on_broker_lane,
    validate_broker_worker_handler_registry,
)

logger = logging.getLogger(__name__)

DEFAULT_BROKER_JOB_LEASE_SECONDS = 300
BROKER_WORKER_IDLE_SLEEP_SECONDS = 5.0
BROKER_WORKER_TICK_ERROR_BACKOFF_SECONDS = 1.0
BROKER_TERMINALIZATION_FAILURE_PREFIX = "broker_terminalization_failure: "


class BrokerNoHandlerForJobKind(LookupError):
    """Raised when ``job_kind`` has no registered handler."""

    def __init__(self, job_kind: str) -> None:
        self.job_kind = job_kind
        super().__init__(f"no Broker job handler registered for job_kind={job_kind!r}")


def default_broker_job_handler_registry() -> dict[str, Callable[[BrokerJobWorkContext], None]]:
    return {}


def process_one_broker_job(
    session_factory: sessionmaker[Session],
    *,
    lease_owner: str,
    job_handlers: Mapping[str, Callable[[BrokerJobWorkContext], None]],
    lease_seconds: int = DEFAULT_BROKER_JOB_LEASE_SECONDS,
    now: datetime | None = None,
) -> Literal["idle", "processed"]:
    when = now if now is not None else datetime.now(timezone.utc)
    lease_until = when + timedelta(seconds=lease_seconds)

    with session_factory() as session:
        with session.begin():
            job = claim_next_eligible_broker_job(
                session,
                lease_owner=lease_owner,
                lease_expires_at=lease_until,
                now=when,
            )
            if job is None:
                return "idle"
            ctx = BrokerJobWorkContext(
                id=job.id,
                job_kind=job.job_kind,
                payload_json=job.payload_json,
                lease_owner=lease_owner,
            )

    if job_kind_forbidden_on_broker_lane(ctx.job_kind):
        err_text = (
            "broker worker refused job_kind reserved for another module lane: "
            f"{ctx.job_kind!r} (row id={ctx.id})"
        )[:10_000]
        try:
            with session_factory() as session:
                with session.begin():
                    fail_claimed_broker_job(
                        session,
                        job_id=ctx.id,
                        lease_owner=ctx.lease_owner,
                        error_message=err_text,
                        now=when,
                    )
        except Exception:
            logger.exception("Broker fail_claimed after cross-lane guard job_id=%s", ctx.id)
        return "processed"

    if not ctx.job_kind.startswith(BROKER_QUEUE_JOB_KIND_PREFIX):
        err_text = (
            "broker worker refused job_kind missing required broker.* prefix: "
            f"{ctx.job_kind!r} (row id={ctx.id})"
        )[:10_000]
        try:
            with session_factory() as session:
                with session.begin():
                    fail_claimed_broker_job(
                        session,
                        job_id=ctx.id,
                        lease_owner=ctx.lease_owner,
                        error_message=err_text,
                        now=when,
                    )
        except Exception:
            logger.exception("Broker fail_claimed after broker.* prefix guard job_id=%s", ctx.id)
        return "processed"

    handler = job_handlers.get(ctx.job_kind)
    if handler is None:
        exc: BaseException = BrokerNoHandlerForJobKind(ctx.job_kind)
        err_text = str(exc)[:10_000]
        try:
            with session_factory() as session:
                with session.begin():
                    fail_claimed_broker_job(
                        session,
                        job_id=ctx.id,
                        lease_owner=ctx.lease_owner,
                        error_message=err_text,
                        now=when,
                    )
        except Exception:
            logger.exception("Broker fail_claimed after missing handler job_id=%s", ctx.id)
        return "processed"

    try:
        handler(ctx)
    except Exception as exc:
        logger.exception("Broker job handler failed for job_id=%s kind=%s", ctx.id, ctx.job_kind)
        err_text = str(exc)[:10_000]
        try:
            with session_factory() as session:
                with session.begin():
                    fail_claimed_broker_job(
                        session,
                        job_id=ctx.id,
                        lease_owner=ctx.lease_owner,
                        error_message=err_text,
                        now=when,
                    )
        except Exception:
            logger.exception("Broker fail_claimed_broker_job failed after handler error job_id=%s", ctx.id)
        return "processed"

    complete_ok = True
    complete_err: str | None = None
    try:
        with session_factory() as session:
            with session.begin():
                ok = complete_claimed_broker_job(
                    session,
                    job_id=ctx.id,
                    lease_owner=ctx.lease_owner,
                    now=when,
                )
                if not ok:
                    complete_ok = False
                    complete_err = "complete_claimed_broker_job refused (lease/state mismatch)"
    except Exception as exc:
        complete_ok = False
        logger.exception("Broker complete_claimed_broker_job failed job_id=%s", ctx.id)
        complete_err = str(exc)

    if not complete_ok and complete_err is not None:
        bounded = (BROKER_TERMINALIZATION_FAILURE_PREFIX + complete_err)[:10_000]
        try:
            with session_factory() as session:
                with session.begin():
                    recovered = fail_leased_broker_job_after_complete_failure(
                        session,
                        job_id=ctx.id,
                        lease_owner=ctx.lease_owner,
                        error_message=bounded,
                        now=when,
                    )
            if not recovered:
                logger.warning(
                    "Broker terminalization recovery did not apply job_id=%s owner=%s",
                    ctx.id,
                    ctx.lease_owner,
                )
        except Exception:
            logger.exception(
                "Broker fail_leased_broker_job_after_complete_failure failed job_id=%s",
                ctx.id,
            )
    return "processed"


def _lease_owner(worker_index: int) -> str:
    return f"{socket.gethostname()}-{os.getpid()}-broker-w{worker_index}"


async def broker_worker_run_forever(
    session_factory: sessionmaker[Session],
    *,
    worker_index: int,
    stop_event: asyncio.Event,
    job_handlers: Mapping[str, Callable[[BrokerJobWorkContext], None]] | None = None,
    idle_sleep_seconds: float = BROKER_WORKER_IDLE_SLEEP_SECONDS,
    lease_seconds: int = DEFAULT_BROKER_JOB_LEASE_SECONDS,
) -> None:
    owner = _lease_owner(worker_index)
    handlers = job_handlers if job_handlers is not None else default_broker_job_handler_registry()
    while not stop_event.is_set():

        def _tick() -> Literal["idle", "processed"]:
            return process_one_broker_job(
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
            logger.exception("Broker worker tick crashed worker_index=%s", worker_index)
            await asyncio.sleep(BROKER_WORKER_TICK_ERROR_BACKOFF_SECONDS)
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


def start_broker_worker_background_tasks(
    session_factory: sessionmaker[Session],
    settings: MediaMopSettings,
    *,
    job_handlers: Mapping[str, Callable[[BrokerJobWorkContext], None]] | None = None,
    stop_event: asyncio.Event | None = None,
) -> tuple[asyncio.Event, list[asyncio.Task[None]]]:
    if settings.broker_worker_count > 1:
        logger.warning(
            "Broker broker_worker_count=%s: multi-worker is guarded under SQLite single-writer.",
            settings.broker_worker_count,
        )

    handlers: Mapping[str, Callable[[BrokerJobWorkContext], None]]
    if job_handlers is not None:
        handlers = job_handlers
    elif settings.broker_worker_count == 0:
        handlers = {}
    else:
        msg = "job_handlers is required when broker_worker_count > 0"
        raise TypeError(msg)

    validate_broker_worker_handler_registry(handlers)

    stop = stop_event if stop_event is not None else asyncio.Event()
    tasks: list[asyncio.Task[None]] = []
    for i in range(settings.broker_worker_count):
        t = asyncio.create_task(
            broker_worker_run_forever(
                session_factory,
                worker_index=i,
                stop_event=stop,
                job_handlers=handlers,
            ),
            name=f"broker-worker-{i}",
        )
        tasks.append(t)
    return stop, tasks


async def stop_broker_worker_background_tasks(
    stop: asyncio.Event,
    tasks: list[asyncio.Task[None]],
) -> None:
    stop.set()
    for t in tasks:
        if not t.done():
            t.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
