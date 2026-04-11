"""Atomic claim / lease / complete / fail for :class:`~mediamop.modules.fetcher.fetcher_jobs_model.FetcherJob`.

SQLite: single-statement ``UPDATE … WHERE id = (SELECT … LIMIT 1)`` makes claims atomic under
the one-writer rule. Callers should keep transactions short.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mediamop.modules.fetcher.fetcher_jobs_model import FetcherJob, FetcherJobStatus
from mediamop.modules.queue_worker.job_kind_boundaries import validate_fetcher_enqueue_job_kind


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


_CLAIM_NEXT_FETCHER_SQL = """
UPDATE fetcher_jobs
SET
  status = :leased,
  lease_owner = :owner,
  lease_expires_at = :lease_exp,
  updated_at = CURRENT_TIMESTAMP,
  attempt_count = attempt_count + 1
WHERE id = (
  SELECT id FROM fetcher_jobs
  WHERE status = :pending
     OR (
       status = :leased
       AND (lease_expires_at IS NULL OR lease_expires_at < :now)
     )
  ORDER BY id ASC
  LIMIT 1
)
RETURNING id
"""


def fetcher_enqueue_or_get_job(
    session: Session,
    *,
    dedupe_key: str,
    job_kind: str,
    payload_json: str | None = None,
    max_attempts: int = 3,
) -> FetcherJob:
    """Insert a ``pending`` job or return the existing row for ``dedupe_key``."""

    validate_fetcher_enqueue_job_kind(job_kind)

    existing = session.scalar(select(FetcherJob).where(FetcherJob.dedupe_key == dedupe_key))
    if existing is not None:
        return existing

    row = FetcherJob(
        dedupe_key=dedupe_key,
        job_kind=job_kind,
        payload_json=payload_json,
        status=FetcherJobStatus.PENDING.value,
        max_attempts=max(1, max_attempts),
    )
    with session.begin_nested():
        session.add(row)
        try:
            session.flush()
        except IntegrityError:
            pass
        else:
            return row

    found = session.scalar(select(FetcherJob).where(FetcherJob.dedupe_key == dedupe_key))
    if found is None:
        msg = "fetcher job dedupe race: row missing after IntegrityError"
        raise RuntimeError(msg)
    return found


def claim_next_eligible_fetcher_job(
    session: Session,
    *,
    lease_owner: str,
    lease_expires_at: datetime,
    now: datetime | None = None,
) -> FetcherJob | None:
    """Atomically lease the next ``pending`` or **expired** ``leased`` row.

    Increments ``attempt_count`` on every successful claim (including reclaim).
    Returns ``None`` if no eligible row exists.
    """

    when = now if now is not None else _utc_now()
    result = session.execute(
        text(_CLAIM_NEXT_FETCHER_SQL),
        {
            "leased": FetcherJobStatus.LEASED.value,
            "pending": FetcherJobStatus.PENDING.value,
            "owner": lease_owner,
            "lease_exp": lease_expires_at,
            "now": when,
        },
    )
    row = result.fetchone()
    if row is None:
        return None
    job_id = int(row[0])
    return session.scalars(select(FetcherJob).where(FetcherJob.id == job_id)).one()


def complete_claimed_fetcher_job(
    session: Session,
    *,
    job_id: int,
    lease_owner: str,
    now: datetime | None = None,
) -> bool:
    """Mark ``completed`` only when ``lease_owner`` matches and lease is still valid."""

    when = now if now is not None else _utc_now()
    job = session.scalars(select(FetcherJob).where(FetcherJob.id == job_id)).one_or_none()
    if job is None:
        return False
    if job.status != FetcherJobStatus.LEASED.value:
        return False
    if job.lease_owner != lease_owner:
        return False
    if job.lease_expires_at is None or job.lease_expires_at < when:
        return False

    job.status = FetcherJobStatus.COMPLETED.value
    job.lease_owner = None
    job.lease_expires_at = None
    session.flush()
    return True


def fail_claimed_fetcher_job(
    session: Session,
    *,
    job_id: int,
    lease_owner: str,
    error_message: str,
    now: datetime | None = None,
) -> bool:
    """After a failed processing attempt: requeue as ``pending`` or mark ``failed`` if attempts exhausted."""

    when = now if now is not None else _utc_now()
    job = session.scalars(select(FetcherJob).where(FetcherJob.id == job_id)).one_or_none()
    if job is None:
        return False
    if job.status != FetcherJobStatus.LEASED.value:
        return False
    if job.lease_owner != lease_owner:
        return False
    if job.lease_expires_at is None or job.lease_expires_at < when:
        return False

    job.last_error = error_message
    job.lease_owner = None
    job.lease_expires_at = None
    if job.attempt_count >= job.max_attempts:
        job.status = FetcherJobStatus.FAILED.value
    else:
        job.status = FetcherJobStatus.PENDING.value
    session.flush()
    return True


def fail_leased_fetcher_job_after_complete_failure(
    session: Session,
    *,
    job_id: int,
    lease_owner: str,
    error_message: str,
    now: datetime | None = None,
) -> bool:
    """Terminal ``handler_ok_finalize_failed`` when the handler succeeded but finalize did not."""

    when = now if now is not None else _utc_now()
    job = session.scalars(select(FetcherJob).where(FetcherJob.id == job_id)).one_or_none()
    if job is None:
        return False
    if job.status != FetcherJobStatus.LEASED.value:
        return False
    if job.lease_owner != lease_owner:
        return False
    if job.lease_expires_at is None or job.lease_expires_at < when:
        return False

    job.status = FetcherJobStatus.HANDLER_OK_FINALIZE_FAILED.value
    job.lease_owner = None
    job.lease_expires_at = None
    job.last_error = error_message[:10_000]
    session.flush()
    return True


def recover_handler_ok_finalize_failed_to_completed(
    session: Session,
    *,
    job_id: int,
    recovered_by_label: str,
    now: datetime | None = None,
) -> Literal["ok", "not_found", "wrong_status"]:
    """Operator recovery: mark ``completed`` without re-running the handler."""

    when = now if now is not None else _utc_now()
    job = session.scalars(select(FetcherJob).where(FetcherJob.id == job_id)).one_or_none()
    if job is None:
        return "not_found"
    if job.status != FetcherJobStatus.HANDLER_OK_FINALIZE_FAILED.value:
        return "wrong_status"

    prev = (job.last_error or "").strip()
    iso = when.isoformat().replace("+00:00", "Z")
    note = (
        f"manual_recover_finalize_failure: marked completed at {iso} by {recovered_by_label} "
        "(handler was not re-run; row was handler_ok_finalize_failed)."
    )
    new_err = f"{prev}\n--- {note}" if prev else note
    job.last_error = new_err[:10_000]
    job.status = FetcherJobStatus.COMPLETED.value
    job.lease_owner = None
    job.lease_expires_at = None
    session.flush()
    return "ok"
