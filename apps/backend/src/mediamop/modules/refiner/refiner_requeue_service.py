"""Putting a failed file back to work — by policy, and by hand.

Refiner deletes source release folders after success. A file that failed recorded an
activity row with a reason and stopped there: no retry, no requeue, no way back. The
asymmetry was the point of #339 — the destructive path was carefully engineered and the
recovery path barely existed.

Two routes back, deliberately different:

**Automatic**, governed by the library's policy. Bounded by ``max_attempts``, delayed by
a doubling backoff, and applied only to failure classes the operator has said are worth
retrying. A file with no retainable audio is not retried, because it will not have grown
one.

**Manual**, which ignores all of that. An operator asking for a retry has usually just
fixed the thing that broke, so making them wait out a backoff — or refusing because the
attempts are spent — would be answering a question they did not ask. A manual requeue
resets the attempt count, and that is the whole difference between the two.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from mediamop.modules.refiner.file_remux_pass.job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from mediamop.modules.refiner.jobs_model import RefinerJob
from mediamop.modules.refiner.jobs_ops import refiner_enqueue_or_get_job
from mediamop.modules.refiner.refiner_failure_classes import (
    RefinerFailureClass,
    backoff_seconds_for_attempt,
    is_retryable,
)
from mediamop.modules.refiner.refiner_file_state_model import RefinerFileRow, RefinerFileStatus
from mediamop.modules.refiner.refiner_library_model import RefinerLibraryRow


@dataclass(frozen=True, slots=True)
class RetryDecision:
    """Whether this failure will be retried, and the sentence explaining it."""

    will_retry: bool
    next_retry_at: datetime | None
    reason: str


def decide_retry(
    *,
    library: RefinerLibraryRow,
    failure_class: RefinerFailureClass | str,
    attempts_so_far: int,
    now: datetime | None = None,
) -> RetryDecision:
    """Apply the library's retry policy to one failure."""

    moment = now or datetime.now(UTC)
    value = (
        failure_class.value if isinstance(failure_class, RefinerFailureClass) else str(failure_class).strip().lower()
    )

    if not is_retryable(
        value,
        retry_preflight_failures=bool(library.retry_preflight_failures),
        retry_execution_failures=bool(library.retry_execution_failures),
    ):
        return RetryDecision(
            will_retry=False,
            next_retry_at=None,
            reason=_not_retryable_reason(value, library),
        )

    max_attempts = max(1, int(library.max_attempts))
    if attempts_so_far >= max_attempts:
        return RetryDecision(
            will_retry=False,
            next_retry_at=None,
            reason=(
                f"MediaMop tried this file {attempts_so_far} times and stopped, because the {library.name} "
                f"library allows {max_attempts}. You can still start it again by hand."
            ),
        )

    # Indexed by failures *so far*, not by the attempt about to happen: after one failure
    # the wait is the configured base, and it doubles from there. Using the next attempt
    # number would skip the base delay entirely and make the first retry twice as slow as
    # the setting says.
    delay = backoff_seconds_for_attempt(
        attempt=attempts_so_far,
        base_seconds=int(library.retry_backoff_seconds),
    )
    when = moment + timedelta(seconds=delay)
    return RetryDecision(
        will_retry=True,
        next_retry_at=when,
        reason=(
            f"This failed and MediaMop will try again in about {delay // 60 or 1} minute(s) "
            f"(attempt {attempts_so_far + 1} of {max_attempts})."
        ),
    )


def _not_retryable_reason(failure_class: str, library: RefinerLibraryRow) -> str:
    if failure_class == RefinerFailureClass.PREFLIGHT.value:
        return (
            "This file was rejected before any work started, so trying again would reach the same "
            "conclusion. Fix what the reason describes, then start it again by hand."
        )
    if failure_class == RefinerFailureClass.GUARDRAIL.value:
        return (
            "A safety check stopped this file. MediaMop does not retry those automatically — the check "
            "is the answer, not something to get past."
        )
    if failure_class == RefinerFailureClass.EXECUTION.value:
        return (
            f"This failed while being processed, and the {library.name} library is set not to retry those. "
            "You can start it again by hand."
        )
    return (
        "MediaMop could not work out why this failed, so it is not retrying automatically. "
        "You can start it again by hand."
    )


def record_failure(
    session: Session,
    *,
    library: RefinerLibraryRow,
    relative_path: str,
    failure_class: RefinerFailureClass | str,
    reason: str,
    now: datetime | None = None,
) -> RetryDecision:
    """Mark a file failed, classify it, and apply the retry policy.

    The decision's sentence becomes the reason on the record, so the screen says whether
    a retry is coming without anyone having to know the policy.
    """

    moment = now or datetime.now(UTC)
    row = session.scalars(
        select(RefinerFileRow)
        .where(RefinerFileRow.library_id == library.id)
        .where(RefinerFileRow.relative_path == relative_path)
    ).first()
    if row is None:
        row = RefinerFileRow(library_id=library.id, relative_path=relative_path)
        session.add(row)
        session.flush()

    attempts = int(row.failure_attempts or 0) + 1
    value = (
        failure_class.value if isinstance(failure_class, RefinerFailureClass) else str(failure_class).strip().lower()
    )
    decision = decide_retry(library=library, failure_class=value, attempts_so_far=attempts, now=moment)

    row.status = RefinerFileStatus.PROCESSING_FAILED.value
    row.status_reason = f"{reason} {decision.reason}".strip()
    row.failure_class = value
    row.failure_attempts = attempts
    row.next_retry_at = decision.next_retry_at
    row.last_attempt_at = moment
    session.flush()
    return decision


@dataclass(frozen=True, slots=True)
class RequeueResult:
    requeued: int
    skipped: int
    detail: str


def _enqueue_remux_for(
    session: Session,
    *,
    library: RefinerLibraryRow,
    row: RefinerFileRow,
    not_before: datetime | None,
) -> RefinerJob:
    payload = json.dumps(
        {
            "relative_media_path": row.relative_path,
            "media_scope": "tv" if library.media_scope == "tv" else "movie",
            "library_id": library.id,
        },
        separators=(",", ":"),
    )
    job = refiner_enqueue_or_get_job(
        session,
        dedupe_key=f"{REFINER_FILE_REMUX_PASS_JOB_KIND}:requeue:{uuid.uuid4().hex}",
        job_kind=REFINER_FILE_REMUX_PASS_JOB_KIND,
        payload_json=payload,
        priority=int(library.priority or 0),
    )
    if not_before is not None:
        job.not_before = not_before
    return job


def requeue_file(
    session: Session,
    *,
    row: RefinerFileRow,
    manual: bool = True,
    now: datetime | None = None,
) -> RequeueResult:
    """Put one file back in the queue.

    ``manual`` resets the attempt count and ignores the backoff, because an operator
    asking for a retry has usually just fixed whatever broke. An automatic requeue keeps
    the count and honours the delay.
    """

    moment = now or datetime.now(UTC)
    library = session.get(RefinerLibraryRow, row.library_id)
    if library is None:
        return RequeueResult(
            requeued=0,
            skipped=1,
            detail="The library this file belonged to no longer exists, so there is nowhere to queue it.",
        )

    if manual:
        row.failure_attempts = 0
        row.failure_class = None
        row.next_retry_at = None
        not_before = None
    else:
        not_before = row.next_retry_at

    _enqueue_remux_for(session, library=library, row=row, not_before=not_before)
    row.status = RefinerFileStatus.UNPROCESSED.value
    row.status_reason = (
        "Queued again by hand. It starts as soon as there is capacity for it."
        if manual
        else "Queued again automatically after a failure."
    )
    session.flush()
    return RequeueResult(requeued=1, skipped=0, detail=row.status_reason)


def requeue_files(
    session: Session,
    *,
    rows: list[RefinerFileRow],
    now: datetime | None = None,
) -> RequeueResult:
    """Requeue a set of files by hand, reporting what actually happened.

    Reports a total rather than raising on the first problem: a bulk action that stops
    halfway leaves an operator guessing which half ran.
    """

    requeued = 0
    skipped = 0
    for row in rows:
        result = requeue_file(session, row=row, manual=True, now=now)
        requeued += result.requeued
        skipped += result.skipped
    if requeued and not skipped:
        detail = f"Queued {requeued} file(s) again. They start as capacity frees up."
    elif requeued:
        detail = f"Queued {requeued} file(s) again. {skipped} could not be queued because their library is gone."
    elif skipped:
        detail = f"Nothing was queued: {skipped} file(s) belong to a library that no longer exists."
    else:
        detail = "Nothing matched, so nothing was queued."
    return RequeueResult(requeued=requeued, skipped=skipped, detail=detail)


def files_due_for_automatic_retry(session: Session, *, now: datetime | None = None) -> list[RefinerFileRow]:
    """Failed files whose backoff has elapsed and whose policy allows another attempt."""

    moment = now or datetime.now(UTC)
    rows = session.scalars(
        select(RefinerFileRow)
        .where(RefinerFileRow.status == RefinerFileStatus.PROCESSING_FAILED.value)
        .where(RefinerFileRow.next_retry_at.is_not(None))
        .order_by(RefinerFileRow.id)
    ).all()
    due: list[RefinerFileRow] = []
    for row in rows:
        when = row.next_retry_at
        if when is None:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        if when <= moment:
            due.append(row)
    return due
