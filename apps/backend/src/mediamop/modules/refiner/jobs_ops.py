"""Atomic claim / lease / complete / fail for :class:`~mediamop.modules.refiner.jobs_model.RefinerJob`.

SQLite: single-statement ``UPDATE … WHERE id = (SELECT … LIMIT 1)`` makes claims atomic under
the one-writer rule. Callers should keep transactions short.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mediamop.modules.refiner.jobs_model import RefinerJob, RefinerJobStatus


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


_CLAIM_NEXT_SQL = """
UPDATE refiner_jobs
SET
  status = :leased,
  lease_owner = :owner,
  lease_expires_at = :lease_exp,
  updated_at = CURRENT_TIMESTAMP,
  attempt_count = attempt_count + 1
WHERE id = (
  SELECT id FROM refiner_jobs
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


def refiner_enqueue_or_get_job(
    session: Session,
    *,
    dedupe_key: str,
    job_kind: str,
    payload_json: str | None = None,
    max_attempts: int = 3,
) -> RefinerJob:
    """Insert a ``pending`` job or return the existing row for ``dedupe_key``."""

    existing = session.scalar(select(RefinerJob).where(RefinerJob.dedupe_key == dedupe_key))
    if existing is not None:
        return existing

    row = RefinerJob(
        dedupe_key=dedupe_key,
        job_kind=job_kind,
        payload_json=payload_json,
        status=RefinerJobStatus.PENDING.value,
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
) -> RefinerJob | None:
    """Atomically lease the next ``pending`` or **expired** ``leased`` row.

    Increments ``attempt_count`` on every successful claim (including reclaim).
    Returns ``None`` if no eligible row exists.
    """

    when = now if now is not None else _utc_now()
    result = session.execute(
        text(_CLAIM_NEXT_SQL),
        {
            "leased": RefinerJobStatus.LEASED.value,
            "pending": RefinerJobStatus.PENDING.value,
            "owner": lease_owner,
            "lease_exp": lease_expires_at,
            "now": when,
        },
    )
    row = result.fetchone()
    if row is None:
        return None
    job_id = int(row[0])
    return session.scalars(select(RefinerJob).where(RefinerJob.id == job_id)).one()


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
    session.flush()
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
    else:
        job.status = RefinerJobStatus.PENDING.value
    session.flush()
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
    return True
