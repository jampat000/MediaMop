"""Atomic claim / lease / complete / fail for :class:`~mediamop.modules.refiner.jobs_model.RefinerJob`.

SQLite: single-statement ``UPDATE … WHERE id = (SELECT … LIMIT 1)`` makes claims atomic under
the one-writer rule. Callers should keep transactions short.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Literal

_REFINER_JOB_DEDUPE_KEY_MAX_LEN = 512

from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mediamop.modules.queue_worker.job_kind_boundaries import validate_refiner_enqueue_job_kind
from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus
from mediamop.platform.metrics.service import record_module_job_event, set_module_queue_depth


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _record_refiner_queue_depth(session: Session) -> None:
    depth = session.scalar(
        select(func.count())
        .select_from(RefinerJob)
        .where(
            or_(RefinerJob.status == RefinerJobStatus.PENDING.value, RefinerJob.status == RefinerJobStatus.LEASED.value)
        )
    )
    set_module_queue_depth(module="refiner", depth=int(depth or 0))


# ``{admission}`` is a predicate built by :func:`_admission_predicate` from ids and job
# kinds this pass may not take. It narrows *which row is chosen*, so a job the schedule
# excludes is never leased — the window gates work, not only enqueue (#337).
_CLAIM_NEXT_SQL_TEMPLATE = """
UPDATE refiner_jobs
SET
  status = :leased,
  lease_owner = :owner,
  lease_expires_at = :lease_exp,
  updated_at = CURRENT_TIMESTAMP,
  attempt_count = attempt_count + 1
WHERE id = (
  SELECT id FROM refiner_jobs
  WHERE (
      (status = :pending AND (not_before IS NULL OR not_before <= :now))
      OR (
        status = :leased
        AND (lease_expires_at IS NULL OR lease_expires_at < :now)
      )
    )
    {admission}
  ORDER BY priority DESC, id ASC
  LIMIT 1
)
RETURNING id
"""


def _admission_predicate(admission: object | None) -> tuple[str, dict[str, object]]:
    """SQL narrowing the claim to work this pass is allowed to start.

    Library ids are formatted into the statement rather than bound, because a variable
    length ``IN`` list cannot be one bound parameter. They are integers read from the
    primary key of a row this process just selected, and each is re-coerced with ``int()``
    here so nothing but a number can reach the string.
    """

    if admission is None:
        return "", {}

    clauses: list[str] = []
    params: dict[str, object] = {}

    blocked: frozenset[int] = getattr(admission, "blocked_library_ids", frozenset())
    ids = sorted({int(x) for x in blocked})
    if ids:
        # A job with no library_id in its payload predates libraries or is suite-wide, so
        # COALESCE keeps it claimable rather than sweeping it up in the exclusion.
        rendered = ",".join(str(i) for i in ids)
        clauses.append(f"AND COALESCE(json_extract(payload_json, '$.library_id'), -1) NOT IN ({rendered})")

    # The weighted budget. A job costing more than what is left waits; a job costing
    # nothing runs even when the budget is full, which is the whole point of weighting
    # rather than counting.
    available = getattr(admission, "available_units", None)
    if available is not None:
        clauses.append("AND runner_cost <= :available_units")
        params["available_units"] = max(0, int(available))

    pause = getattr(admission, "pause", None)
    if pause is not None and getattr(pause, "paused", False):
        from mediamop.modules.refiner.refiner_work_admission import DETECTION_JOB_KIND_PREFIXES

        if getattr(pause, "scan_while_paused", False):
            # Detection continues; processing does not. Prefix matching keeps this in step
            # with the job-kind naming rather than an enumerated list that drifts.
            likes = []
            for index, prefix in enumerate(DETECTION_JOB_KIND_PREFIXES):
                key = f"detect_{index}"
                likes.append(f"job_kind LIKE :{key}")
                params[key] = f"{prefix}%"
            clauses.append(f"AND ({' OR '.join(likes)})")
        else:
            # Nothing at all.
            clauses.append("AND 1 = 0")

    if not clauses:
        return "", params
    return "\n    " + "\n    ".join(clauses), params


def _tombstone_cancelled_dedupe_key(*, original: str, job_id: int) -> str:
    """Rewrite ``dedupe_key`` so the original key can be reused for a new enqueue."""

    suffix = f":cancelled:{job_id}"
    base = (original or "")[: max(0, _REFINER_JOB_DEDUPE_KEY_MAX_LEN - len(suffix))]
    out = f"{base}{suffix}"
    return out[:_REFINER_JOB_DEDUPE_KEY_MAX_LEN]


def cancel_pending_refiner_job(session: Session, *, job_id: int) -> Literal["ok", "not_found", "wrong_status"]:
    """Operator abandon: only ``pending`` rows; refuses leased/completed/failed/cancelled.

    Rewrites ``dedupe_key`` to a tombstone so a later enqueue may reuse the operator-facing
    dedupe string. Does not touch Activity (no job had run yet for typical cancel use).
    """

    job = session.scalars(select(RefinerJob).where(RefinerJob.id == job_id)).one_or_none()
    if job is None:
        return "not_found"
    if job.status != RefinerJobStatus.PENDING.value:
        return "wrong_status"

    job.dedupe_key = _tombstone_cancelled_dedupe_key(original=job.dedupe_key, job_id=job.id)
    job.status = RefinerJobStatus.CANCELLED.value
    job.lease_owner = None
    job.lease_expires_at = None
    job.last_error = "Cancelled by operator before a worker claimed this job."
    session.flush()
    return "ok"


def refiner_enqueue_or_get_job(
    session: Session,
    *,
    dedupe_key: str,
    job_kind: str,
    payload_json: str | None = None,
    max_attempts: int = 3,
    runner_cost: int = 0,
    priority: int = 0,
) -> RefinerJob:
    """Insert a ``pending`` job or return the existing row for ``dedupe_key``.

    ``runner_cost`` is fixed here rather than at lease time: the claim has to answer
    "does this fit in what is left?" in one statement, and a row carrying its own cost
    makes that a comparison instead of a join against a probe result that may not exist.
    """

    validate_refiner_enqueue_job_kind(job_kind)

    existing = session.scalar(select(RefinerJob).where(RefinerJob.dedupe_key == dedupe_key))
    if existing is not None:
        return existing

    row = RefinerJob(
        dedupe_key=dedupe_key,
        job_kind=job_kind,
        payload_json=payload_json,
        status=RefinerJobStatus.PENDING.value,
        max_attempts=max(1, max_attempts),
        runner_cost=max(0, int(runner_cost)),
        priority=int(priority),
    )
    with session.begin_nested():
        session.add(row)
        try:
            session.flush()
        except IntegrityError:
            pass
        else:
            _record_refiner_queue_depth(session)
            return row

    found = session.scalar(select(RefinerJob).where(RefinerJob.dedupe_key == dedupe_key))
    if found is None:
        msg = "refiner job dedupe race: row missing after IntegrityError"
        raise RuntimeError(msg)
    return found


def claim_next_eligible_refiner_job(
    session: Session,
    *,
    lease_owner: str,
    lease_expires_at: datetime,
    now: datetime | None = None,
    admission: object | None = None,
) -> RefinerJob | None:
    """Atomically lease the next ``pending`` or **expired** ``leased`` row.

    Increments ``attempt_count`` on every successful claim (including reclaim).
    Returns ``None`` if no eligible row exists.

    ``admission`` narrows what may be claimed to what the schedule and the suite pause
    currently allow. Passing ``None`` claims exactly as before, which is what every
    caller that has nothing to do with scheduling wants.
    """

    when = now if now is not None else _utc_now()
    predicate, extra = _admission_predicate(admission)
    result = session.execute(
        text(_CLAIM_NEXT_SQL_TEMPLATE.format(admission=predicate)),
        {
            "leased": RefinerJobStatus.LEASED.value,
            "pending": RefinerJobStatus.PENDING.value,
            "owner": lease_owner,
            "lease_exp": lease_expires_at,
            "now": when,
            **extra,
        },
    )
    row = result.fetchone()
    if row is None:
        return None
    job_id = int(row[0])
    claimed = session.scalars(select(RefinerJob).where(RefinerJob.id == job_id)).one()
    record_module_job_event(module="refiner", event="started")
    _record_refiner_queue_depth(session)
    return claimed


def complete_claimed_refiner_job(
    session: Session,
    *,
    job_id: int,
    lease_owner: str,
    now: datetime | None = None,
) -> bool:
    """Mark ``completed`` only when ``lease_owner`` matches and lease is still valid."""

    when = now if now is not None else _utc_now()
    job = session.scalars(select(RefinerJob).where(RefinerJob.id == job_id)).one_or_none()
    if job is None:
        return False
    if job.status != RefinerJobStatus.LEASED.value:
        return False
    if job.lease_owner != lease_owner:
        return False
    if job.lease_expires_at is None or job.lease_expires_at < when:
        return False

    job.status = RefinerJobStatus.COMPLETED.value
    job.lease_owner = None
    job.lease_expires_at = None
    job.last_error = None
    session.flush()
    record_module_job_event(module="refiner", event="completed")
    _record_refiner_queue_depth(session)
    return True


def fail_claimed_refiner_job(
    session: Session,
    *,
    job_id: int,
    lease_owner: str,
    error_message: str,
    now: datetime | None = None,
) -> bool:
    """After a failed processing attempt: requeue as ``pending`` or mark ``failed`` if attempts exhausted."""

    when = now if now is not None else _utc_now()
    job = session.scalars(select(RefinerJob).where(RefinerJob.id == job_id)).one_or_none()
    if job is None:
        return False
    if job.status != RefinerJobStatus.LEASED.value:
        return False
    if job.lease_owner != lease_owner:
        return False
    if job.lease_expires_at is None or job.lease_expires_at < when:
        return False

    job.last_error = error_message
    job.lease_owner = None
    job.lease_expires_at = None
    if job.attempt_count >= job.max_attempts:
        job.status = RefinerJobStatus.FAILED.value
        job.not_before = None
        record_module_job_event(module="refiner", event="failed")
    else:
        job.status = RefinerJobStatus.PENDING.value
        delay = min(30 * (2 ** (job.attempt_count - 1)), 1800)
        job.not_before = when + timedelta(seconds=delay)
    session.flush()
    _record_refiner_queue_depth(session)
    return True


def fail_leased_refiner_job_after_complete_failure(
    session: Session,
    *,
    job_id: int,
    lease_owner: str,
    error_message: str,
    now: datetime | None = None,
) -> bool:
    """Terminal ``handler_ok_finalize_failed`` when the handler succeeded but finalize did not.

    Same lease guards as :func:`complete_claimed_refiner_job`. Clears the lease, sets
    ``last_error``, and does **not** change ``attempt_count``. Not claimable by the normal worker
    claim path (distinct from ordinary ``failed`` after handler errors).
    """

    when = now if now is not None else _utc_now()
    job = session.scalars(select(RefinerJob).where(RefinerJob.id == job_id)).one_or_none()
    if job is None:
        return False
    if job.status != RefinerJobStatus.LEASED.value:
        return False
    if job.lease_owner != lease_owner:
        return False
    if job.lease_expires_at is None or job.lease_expires_at < when:
        return False

    job.status = RefinerJobStatus.HANDLER_OK_FINALIZE_FAILED.value
    job.lease_owner = None
    job.lease_expires_at = None
    job.last_error = error_message[:10_000]
    session.flush()
    record_module_job_event(module="refiner", event="failed")
    _record_refiner_queue_depth(session)
    return True


def recover_handler_ok_finalize_failed_to_completed(
    session: Session,
    *,
    job_id: int,
    recovered_by_label: str,
    now: datetime | None = None,
) -> Literal["ok", "not_found", "wrong_status"]:
    """Operator recovery: mark ``completed`` without re-running the handler.

    Only rows in ``handler_ok_finalize_failed`` are eligible. Appends an audit line to
    ``last_error`` (preserving prior finalize context), clears any lease fields, leaves
    ``attempt_count`` unchanged.
    """

    when = now if now is not None else _utc_now()
    job = session.scalars(select(RefinerJob).where(RefinerJob.id == job_id)).one_or_none()
    if job is None:
        return "not_found"
    if job.status != RefinerJobStatus.HANDLER_OK_FINALIZE_FAILED.value:
        return "wrong_status"

    prev = (job.last_error or "").strip()
    iso = when.isoformat().replace("+00:00", "Z")
    note = (
        f"manual_recover_finalize_failure: marked completed at {iso} by {recovered_by_label} "
        "(handler was not re-run; row was handler_ok_finalize_failed)."
    )
    new_err = f"{prev}\n--- {note}" if prev else note
    job.last_error = new_err[:10_000]
    job.status = RefinerJobStatus.COMPLETED.value
    job.lease_owner = None
    job.lease_expires_at = None
    session.flush()
    record_module_job_event(module="refiner", event="completed")
    _record_refiner_queue_depth(session)
    return "ok"


def move_refiner_job_to_top(session: Session, *, job_id: int) -> Literal["ok", "not_found", "wrong_status"]:
    """Put one queued job ahead of everything else waiting.

    Only ``pending`` rows: a leased job is already running, and "move to top" cannot
    make something that has started start earlier. Raising it above the current maximum
    rather than to a fixed number means two files moved to the top keep the order they
    were moved in.
    """

    job = session.scalars(select(RefinerJob).where(RefinerJob.id == job_id)).one_or_none()
    if job is None:
        return "not_found"
    if job.status != RefinerJobStatus.PENDING.value:
        return "wrong_status"
    highest = session.scalar(
        select(func.max(RefinerJob.priority)).where(RefinerJob.status == RefinerJobStatus.PENDING.value)
    )
    job.priority = int(highest or 0) + 1
    session.flush()
    return "ok"
