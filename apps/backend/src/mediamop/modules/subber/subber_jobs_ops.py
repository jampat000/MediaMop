"""Atomic claim / lease / complete / fail for :class:`~mediamop.modules.subber.subber_jobs_model.SubberJob`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mediamop.modules.queue_worker.job_kind_boundaries import validate_subber_enqueue_job_kind
from mediamop.modules.subber.subber_jobs_model import SubberJob, SubberJobStatus
from mediamop.platform.metrics.service import record_module_job_event, set_module_queue_depth


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _record_subber_queue_depth(session: Session) -> None:
    depth = session.scalar(
        select(func.count())
        .select_from(SubberJob)
        .where(or_(SubberJob.status == SubberJobStatus.PENDING.value, SubberJob.status == SubberJobStatus.LEASED.value))
    )
    set_module_queue_depth(module="subber", depth=int(depth or 0))


_CLAIM_NEXT_SQL = """
UPDATE subber_jobs
SET
  status = :leased,
  lease_owner = :owner,
  lease_expires_at = :lease_exp,
  updated_at = CURRENT_TIMESTAMP,
  attempt_count = attempt_count + 1
WHERE id = (
  SELECT id FROM subber_jobs
  WHERE (status = :pending AND (not_before IS NULL OR not_before <= :now))
     OR (
       status = :leased
       AND (lease_expires_at IS NULL OR lease_expires_at < :now)
     )
  ORDER BY id ASC
  LIMIT 1
)
RETURNING id
"""


def subber_enqueue_or_get_job(
    session: Session,
    *,
    dedupe_key: str,
    job_kind: str,
    payload_json: str | None = None,
    max_attempts: int = 3,
) -> SubberJob:
    """Insert a ``pending`` job or return the existing row for ``dedupe_key``."""

    validate_subber_enqueue_job_kind(job_kind)

    existing = session.scalar(select(SubberJob).where(SubberJob.dedupe_key == dedupe_key))
    if existing is not None:
        return existing

    row = SubberJob(
        dedupe_key=dedupe_key,
        job_kind=job_kind,
        payload_json=payload_json,
        status=SubberJobStatus.PENDING.value,
        max_attempts=max(1, max_attempts),
    )
    with session.begin_nested():
        session.add(row)
        try:
            session.flush()
        except IntegrityError:
            pass
        else:
            _record_subber_queue_depth(session)
            return row

    found = session.scalar(select(SubberJob).where(SubberJob.dedupe_key == dedupe_key))
    if found is None:
        msg = "subber job dedupe race: row missing after IntegrityError"
        raise RuntimeError(msg)
    return found


def claim_next_eligible_subber_job(
    session: Session,
    *,
    lease_owner: str,
    lease_expires_at: datetime,
    now: datetime | None = None,
) -> SubberJob | None:
    when = now if now is not None else _utc_now()
    result = session.execute(
        text(_CLAIM_NEXT_SQL),
        {
            "leased": SubberJobStatus.LEASED.value,
            "pending": SubberJobStatus.PENDING.value,
            "owner": lease_owner,
            "lease_exp": lease_expires_at,
            "now": when,
        },
    )
    row = result.fetchone()
    if row is None:
        return None
    job_id = int(row[0])
    claimed = session.scalars(select(SubberJob).where(SubberJob.id == job_id)).one()
    record_module_job_event(module="subber", event="started")
    _record_subber_queue_depth(session)
    return claimed


def complete_claimed_subber_job(
    session: Session,
    *,
    job_id: int,
    lease_owner: str,
    now: datetime | None = None,
) -> bool:
    when = now if now is not None else _utc_now()
    job = session.scalars(select(SubberJob).where(SubberJob.id == job_id)).one_or_none()
    if job is None:
        return False
    if job.status != SubberJobStatus.LEASED.value:
        return False
    if job.lease_owner != lease_owner:
        return False
    if job.lease_expires_at is None or job.lease_expires_at < when:
        return False

    job.status = SubberJobStatus.COMPLETED.value
    job.lease_owner = None
    job.lease_expires_at = None
    session.flush()
    record_module_job_event(module="subber", event="completed")
    _record_subber_queue_depth(session)
    return True


def fail_claimed_subber_job(
    session: Session,
    *,
    job_id: int,
    lease_owner: str,
    error_message: str,
    now: datetime | None = None,
) -> bool:
    when = now if now is not None else _utc_now()
    job = session.scalars(select(SubberJob).where(SubberJob.id == job_id)).one_or_none()
    if job is None:
        return False
    if job.status != SubberJobStatus.LEASED.value:
        return False
    if job.lease_owner != lease_owner:
        return False
    if job.lease_expires_at is None or job.lease_expires_at < when:
        return False

    job.last_error = error_message
    job.lease_owner = None
    job.lease_expires_at = None
    if job.attempt_count >= job.max_attempts:
        job.status = SubberJobStatus.FAILED.value
        job.not_before = None
        record_module_job_event(module="subber", event="failed")
    else:
        job.status = SubberJobStatus.PENDING.value
        delay = min(30 * (2 ** (job.attempt_count - 1)), 1800)
        job.not_before = when + timedelta(seconds=delay)
    session.flush()
    _record_subber_queue_depth(session)
    return True


def fail_leased_subber_job_after_complete_failure(
    session: Session,
    *,
    job_id: int,
    lease_owner: str,
    error_message: str,
    now: datetime | None = None,
) -> bool:
    when = now if now is not None else _utc_now()
    job = session.scalars(select(SubberJob).where(SubberJob.id == job_id)).one_or_none()
    if job is None:
        return False
    if job.status != SubberJobStatus.LEASED.value:
        return False
    if job.lease_owner != lease_owner:
        return False
    if job.lease_expires_at is None or job.lease_expires_at < when:
        return False

    job.status = SubberJobStatus.HANDLER_OK_FINALIZE_FAILED.value
    job.lease_owner = None
    job.lease_expires_at = None
    job.last_error = error_message[:10_000]
    session.flush()
    record_module_job_event(module="subber", event="failed")
    _record_subber_queue_depth(session)
    return True
