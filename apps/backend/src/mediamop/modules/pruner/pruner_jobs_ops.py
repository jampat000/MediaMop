"""Atomic claim / lease / complete / fail for :class:`~mediamop.modules.pruner.pruner_jobs_model.PrunerJob`."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mediamop.modules.queue_worker.job_kind_boundaries import validate_pruner_enqueue_job_kind
from mediamop.modules.pruner.pruner_jobs_model import PrunerJob, PrunerJobStatus


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


_CLAIM_NEXT_SQL = """
UPDATE pruner_jobs
SET
  status = :leased,
  lease_owner = :owner,
  lease_expires_at = :lease_exp,
  updated_at = CURRENT_TIMESTAMP,
  attempt_count = attempt_count + 1
WHERE id = (
  SELECT id FROM pruner_jobs
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


def pruner_enqueue_or_get_job(
    session: Session,
    *,
    dedupe_key: str,
    job_kind: str,
    payload_json: str | None = None,
    max_attempts: int = 3,
) -> PrunerJob:
    """Insert a ``pending`` job or return the existing row for ``dedupe_key``."""

    validate_pruner_enqueue_job_kind(job_kind)

    existing = session.scalar(select(PrunerJob).where(PrunerJob.dedupe_key == dedupe_key))
    if existing is not None:
        return existing

    row = PrunerJob(
        dedupe_key=dedupe_key,
        job_kind=job_kind,
        payload_json=payload_json,
        status=PrunerJobStatus.PENDING.value,
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

    found = session.scalar(select(PrunerJob).where(PrunerJob.dedupe_key == dedupe_key))
    if found is None:
        msg = "pruner job dedupe race: row missing after IntegrityError"
        raise RuntimeError(msg)
    return found


def claim_next_eligible_pruner_job(
    session: Session,
    *,
    lease_owner: str,
    lease_expires_at: datetime,
    now: datetime | None = None,
) -> PrunerJob | None:
    """Atomically lease the next ``pending`` or expired ``leased`` row."""

    when = now if now is not None else _utc_now()
    result = session.execute(
        text(_CLAIM_NEXT_SQL),
        {
            "leased": PrunerJobStatus.LEASED.value,
            "pending": PrunerJobStatus.PENDING.value,
            "owner": lease_owner,
            "lease_exp": lease_expires_at,
            "now": when,
        },
    )
    row = result.fetchone()
    if row is None:
        return None
    job_id = int(row[0])
    return session.scalars(select(PrunerJob).where(PrunerJob.id == job_id)).one()


def complete_claimed_pruner_job(
    session: Session,
    *,
    job_id: int,
    lease_owner: str,
    now: datetime | None = None,
) -> bool:
    """Mark ``completed`` only when ``lease_owner`` matches and lease is still valid."""

    when = now if now is not None else _utc_now()
    job = session.scalars(select(PrunerJob).where(PrunerJob.id == job_id)).one_or_none()
    if job is None:
        return False
    if job.status != PrunerJobStatus.LEASED.value:
        return False
    if job.lease_owner != lease_owner:
        return False
    if job.lease_expires_at is None or job.lease_expires_at < when:
        return False

    job.status = PrunerJobStatus.COMPLETED.value
    job.lease_owner = None
    job.lease_expires_at = None
    session.flush()
    return True


def fail_claimed_pruner_job(
    session: Session,
    *,
    job_id: int,
    lease_owner: str,
    error_message: str,
    now: datetime | None = None,
) -> bool:
    """After a failed processing attempt: requeue as ``pending`` or mark ``failed`` if attempts exhausted."""

    when = now if now is not None else _utc_now()
    job = session.scalars(select(PrunerJob).where(PrunerJob.id == job_id)).one_or_none()
    if job is None:
        return False
    if job.status != PrunerJobStatus.LEASED.value:
        return False
    if job.lease_owner != lease_owner:
        return False
    if job.lease_expires_at is None or job.lease_expires_at < when:
        return False

    job.last_error = error_message
    job.lease_owner = None
    job.lease_expires_at = None
    if job.attempt_count >= job.max_attempts:
        job.status = PrunerJobStatus.FAILED.value
    else:
        job.status = PrunerJobStatus.PENDING.value
    session.flush()
    return True


def fail_leased_pruner_job_after_complete_failure(
    session: Session,
    *,
    job_id: int,
    lease_owner: str,
    error_message: str,
    now: datetime | None = None,
) -> bool:
    """Terminal handler_ok_finalize_failed when finalize after a successful handler did not apply."""

    when = now if now is not None else _utc_now()
    job = session.scalars(select(PrunerJob).where(PrunerJob.id == job_id)).one_or_none()
    if job is None:
        return False
    if job.status != PrunerJobStatus.LEASED.value:
        return False
    if job.lease_owner != lease_owner:
        return False
    if job.lease_expires_at is None or job.lease_expires_at < when:
        return False

    job.status = PrunerJobStatus.HANDLER_OK_FINALIZE_FAILED.value
    job.lease_owner = None
    job.lease_expires_at = None
    job.last_error = error_message[:10_000]
    session.flush()
    return True
