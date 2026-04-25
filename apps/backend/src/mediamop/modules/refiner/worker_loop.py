"""Refiner-only in-process asyncio worker loop.

Claims rows from ``refiner_jobs`` only, dispatches by ``job_kind``, then completes or fails via
:class:`mediamop.modules.refiner.jobs_ops`.
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
from mediamop.platform.http.request_context import job_logging_context
from mediamop.modules.queue_worker.job_kind_boundaries import (
    REFINER_QUEUE_JOB_KIND_PREFIX,
    job_kind_forbidden_on_refiner_lane,
    validate_refiner_worker_handler_registry,
)
from mediamop.modules.refiner.jobs_ops import (
    claim_next_eligible_refiner_job,
    complete_claimed_refiner_job,
    fail_claimed_refiner_job,
    fail_leased_refiner_job_after_complete_failure,
)

logger = logging.getLogger(__name__)

DEFAULT_REFINER_JOB_LEASE_SECONDS = 300
REFINER_WORKER_IDLE_SLEEP_SECONDS = 5.0
REFINER_WORKER_TICK_ERROR_BACKOFF_SECONDS = 1.0
REFINER_TERMINALIZATION_FAILURE_PREFIX = "refiner_terminalization_failure: "


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

    if job_kind_forbidden_on_refiner_lane(ctx.job_kind):
        err_text = (
            "refiner worker refused job_kind reserved for another module lane: "
            f"{ctx.job_kind!r} (row id={ctx.id}); use the correct table + workers for that prefix"
        )[:10_000]
        try:
            with session_factory() as session:
                with session.begin():
                    fail_claimed_refiner_job(
                        session,
                        job_id=ctx.id,
                        lease_owner=ctx.lease_owner,
                        error_message=err_text,
                        now=when,
                    )
        except Exception:
            logger.exception(
                "Refiner fail_claimed after cross-lane job_kind guard job_id=%s",
                ctx.id,
            )
        return "processed"

    if not ctx.job_kind.startswith(REFINER_QUEUE_JOB_KIND_PREFIX):
        err_text = (
            "refiner worker refused job_kind missing required refiner.* prefix: "
            f"{ctx.job_kind!r} (row id={ctx.id}); enqueue only refiner-owned kinds"
        )[:10_000]
        try:
            with session_factory() as session:
                with session.begin():
                    fail_claimed_refiner_job(
                        session,
                        job_id=ctx.id,
                        lease_owner=ctx.lease_owner,
                        error_message=err_text,
                        now=when,
                    )
        except Exception:
            logger.exception(
                "Refiner fail_claimed after refiner.* prefix guard job_id=%s",
                ctx.id,
            )
        return "processed"

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
                        now=when,
                    )
        except Exception:
            logger.exception(
                "Refiner fail_claimed_refiner_job failed after missing handler job_id=%s",
                ctx.id,
            )
        return "processed"

    try:
        with job_logging_context(ctx.id):
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
                        now=when,
                    )
        except Exception:
            logger.exception(
                "Refiner fail_claimed_refiner_job failed after handler error job_id=%s",
                ctx.id,
            )
        return "processed"

    complete_ok = True
    complete_err: str | None = None
    try:
        with session_factory() as session:
            with session.begin():
                ok = complete_claimed_refiner_job(
                    session,
                    job_id=ctx.id,
                    lease_owner=ctx.lease_owner,
                    now=when,
                )
                if not ok:
                    complete_ok = False
                    complete_err = "complete_claimed_refiner_job refused (lease/state mismatch)"
    except Exception as exc:
        complete_ok = False
        logger.exception("Refiner complete_claimed_refiner_job failed job_id=%s", ctx.id)
        complete_err = str(exc)

    if not complete_ok and complete_err is not None:
        bounded = (REFINER_TERMINALIZATION_FAILURE_PREFIX + complete_err)[:10_000]
        try:
            with session_factory() as session:
                with session.begin():
                    recovered = fail_leased_refiner_job_after_complete_failure(
                        session,
                        job_id=ctx.id,
                        lease_owner=ctx.lease_owner,
                        error_message=bounded,
                        now=when,
                    )
            if not recovered:
                logger.warning(
                    "Refiner terminalization recovery did not apply job_id=%s owner=%s",
                    ctx.id,
                    ctx.lease_owner,
                )
        except Exception:
            logger.exception(
                "Refiner fail_leased_refiner_job_after_complete_failure failed job_id=%s",
                ctx.id,
            )
    return "processed"


def _lease_owner(worker_index: int) -> str:
    return f"{socket.gethostname()}-{os.getpid()}-w{worker_index}"


async def refiner_worker_run_forever(
    session_factory: sessionmaker[Session],
    *,
    worker_index: int,
    stop_event: asyncio.Event,
    job_handlers: Mapping[str, Callable[[RefinerJobWorkContext], None]] | None = None,
    max_concurrent_files_getter: Callable[[], int] | None = None,
    idle_sleep_seconds: float = REFINER_WORKER_IDLE_SLEEP_SECONDS,
    lease_seconds: int = DEFAULT_REFINER_JOB_LEASE_SECONDS,
) -> None:
    """One asyncio task: repeatedly process jobs until ``stop_event`` is set."""

    owner = _lease_owner(worker_index)
    handlers = job_handlers if job_handlers is not None else default_refiner_job_handler_registry()
    while not stop_event.is_set():
        if max_concurrent_files_getter is not None:
            try:
                max_concurrent = max(1, min(8, int(max_concurrent_files_getter())))
            except Exception:
                max_concurrent = 1
            if worker_index >= max_concurrent:
                loop = asyncio.get_running_loop()
                deadline = loop.time() + idle_sleep_seconds
                while loop.time() < deadline and not stop_event.is_set():
                    remaining = deadline - loop.time()
                    if remaining <= 0:
                        break
                    await asyncio.sleep(min(0.25, remaining))
                continue

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
    max_concurrent_files_getter: Callable[[], int] | None = None,
    stop_event: asyncio.Event | None = None,
) -> tuple[asyncio.Event, list[asyncio.Task[None]]]:
    """Create Refiner worker slots and let operator settings control active file concurrency.

    When ``refiner_worker_count > 0``, callers must pass ``job_handlers`` (built at the application
    composition root).

    Modes:

    - **0** — Returns an empty task list (workers intentionally off; lifespan still stops cleanly).
    - **1** — One available worker slot.
    - **>1** — Multiple available worker slots; ``max_concurrent_files_getter`` gates the active slots
      from the user-facing "Files at once" setting while SQLite still serializes writes.
    """

    if settings.refiner_worker_count > 1:
        logger.warning(
            "Refiner refiner_worker_count=%s: multi-worker is a guarded capability under SQLite "
            "(single-writer database). The user-facing files-at-once setting gates active slots.",
            settings.refiner_worker_count,
        )

    handlers: Mapping[str, Callable[[RefinerJobWorkContext], None]]
    if job_handlers is not None:
        handlers = job_handlers
    elif settings.refiner_worker_count == 0:
        handlers = {}
    else:
        msg = "job_handlers is required when refiner_worker_count > 0"
        raise TypeError(msg)

    validate_refiner_worker_handler_registry(handlers)

    stop = stop_event if stop_event is not None else asyncio.Event()
    tasks: list[asyncio.Task[None]] = []
    # ``refiner_worker_count`` is an internal startup slot cap. In normal app usage it is 8, and
    # ``max_concurrent_files_getter`` makes the saved "Files at once" value the effective worker count.
    worker_slots = int(settings.refiner_worker_count)
    for i in range(worker_slots):
        t = asyncio.create_task(
            refiner_worker_run_forever(
                session_factory,
                worker_index=i,
                stop_event=stop,
                job_handlers=handlers,
                max_concurrent_files_getter=max_concurrent_files_getter,
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
