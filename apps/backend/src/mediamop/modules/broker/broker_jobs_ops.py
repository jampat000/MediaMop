"""Atomic claim / lease / complete / fail for :class:`~mediamop.modules.broker.broker_jobs_model.BrokerJob`."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mediamop.modules.broker.broker_jobs_model import BrokerJob, BrokerJobStatus
from mediamop.modules.queue_worker.job_kind_boundaries import validate_broker_enqueue_job_kind


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


_CLAIM_NEXT_SQL = """
UPDATE broker_jobs
SET
  status = :leased,
  lease_owner = :owner,
  lease_expires_at = :lease_exp,
  updated_at = CURRENT_TIMESTAMP,
  attempt_count = attempt_count + 1
WHERE id = (
  SELECT id FROM broker_jobs
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


def broker_enqueue_or_get_job(
    session: Session,
    *,
    dedupe_key: str,
    job_kind: str,
    payload_json: str | None = None,
    max_attempts: int = 3,
) -> BrokerJob:
    """Insert a ``pending`` job or return the existing row for ``dedupe_key``."""

    validate_broker_enqueue_job_kind(job_kind)

    existing = session.scalar(select(BrokerJob).where(BrokerJob.dedupe_key == dedupe_key))
    if existing is not None:
        return existing

    row = BrokerJob(
        dedupe_key=dedupe_key,
        job_kind=job_kind,
        payload_json=payload_json,
        status=BrokerJobStatus.PENDING.value,
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

    found = session.scalar(select(BrokerJob).where(BrokerJob.dedupe_key == dedupe_key))
    if found is None:
        msg = "broker job dedupe race: row missing after IntegrityError"
        raise RuntimeError(msg)
    return found


def claim_next_eligible_broker_job(
    session: Session,
    *,
    lease_owner: str,
    lease_expires_at: datetime,
    now: datetime | None = None,
) -> BrokerJob | None:
    when = now if now is not None else _utc_now()
    result = session.execute(
        text(_CLAIM_NEXT_SQL),
        {
            "leased": BrokerJobStatus.LEASED.value,
            "pending": BrokerJobStatus.PENDING.value,
            "owner": lease_owner,
            "lease_exp": lease_expires_at,
            "now": when,
        },
    )
    row = result.fetchone()
    if row is None:
        return None
    job_id = int(row[0])
    return session.scalars(select(BrokerJob).where(BrokerJob.id == job_id)).one()


def complete_claimed_broker_job(
    session: Session,
    *,
    job_id: int,
    lease_owner: str,
    now: datetime | None = None,
) -> bool:
    when = now if now is not None else _utc_now()
    job = session.scalars(select(BrokerJob).where(BrokerJob.id == job_id)).one_or_none()
    if job is None:
        return False
    if job.status != BrokerJobStatus.LEASED.value:
        return False
    if job.lease_owner != lease_owner:
        return False
    if job.lease_expires_at is None or job.lease_expires_at < when:
        return False

    job.status = BrokerJobStatus.COMPLETED.value
    job.lease_owner = None
    job.lease_expires_at = None
    session.flush()
    return True


def fail_claimed_broker_job(
    session: Session,
    *,
    job_id: int,
    lease_owner: str,
    error_message: str,
    now: datetime | None = None,
) -> bool:
    when = now if now is not None else _utc_now()
    job = session.scalars(select(BrokerJob).where(BrokerJob.id == job_id)).one_or_none()
    if job is None:
        return False
    if job.status != BrokerJobStatus.LEASED.value:
        return False
    if job.lease_owner != lease_owner:
        return False
    if job.lease_expires_at is None or job.lease_expires_at < when:
        return False

    job.last_error = error_message
    job.lease_owner = None
    job.lease_expires_at = None
    if job.attempt_count >= job.max_attempts:
        job.status = BrokerJobStatus.FAILED.value
    else:
        job.status = BrokerJobStatus.PENDING.value
    session.flush()
    return True


def fail_leased_broker_job_after_complete_failure(
    session: Session,
    *,
    job_id: int,
    lease_owner: str,
    error_message: str,
    now: datetime | None = None,
) -> bool:
    when = now if now is not None else _utc_now()
    job = session.scalars(select(BrokerJob).where(BrokerJob.id == job_id)).one_or_none()
    if job is None:
        return False
    if job.status != BrokerJobStatus.LEASED.value:
        return False
    if job.lease_owner != lease_owner:
        return False
    if job.lease_expires_at is None or job.lease_expires_at < when:
        return False

    job.status = BrokerJobStatus.HANDLER_OK_FINALIZE_FAILED.value
    job.lease_owner = None
    job.lease_expires_at = None
    job.last_error = error_message[:10_000]
    session.flush()
    return True
