"""What Weir can tell a media manager about a hand-off it gave us (#480, Deluno#511).

Deluno no longer gives up on a hand-off after a fixed time. It asks instead, and decides from the
answer whether to keep waiting. So the answer has to be honest in both directions: a file that is
simply waiting its turn must never read as stalled, and a hand-off Weir really did finish must
never read as unknown.

The state is worked out **live** from the job queue and the Files row whenever those still exist,
because they are the truth. The ledger row keeps the last answer so it survives job-row pruning and
"clear history". The vocabulary is the one agreed with Deluno:

``queued`` · ``scheduled`` · ``working`` · ``completed`` · ``passed-through`` · ``failed`` ·
``rejected`` · ``cancelled``

``last_changed_at`` moves when Weir's state for the file changes — a retry attempt, work
starting, a result — and not on every poll or progress tick, because Deluno reads "has not moved
for N hours" as a stall.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from weir.platform.media_managers.handoff_ledger_model import MediaManagerHandoffRow
from weir.refiner.file_remux_pass.job_kinds import REFINER_FILE_REMUX_PASS_JOB_KIND
from weir.refiner.jobs_model import RefinerJob, RefinerJobStatus
from weir.refiner.jobs_ops import cancel_pending_refiner_job
from weir.refiner.refiner_failure_policy_job_kinds import (
    REFINER_FILE_PASS_THROUGH_JOB_KIND,
    REFINER_FILE_REJECT_JOB_KIND,
)
from weir.refiner.refiner_file_state_model import RefinerFileRow, RefinerFileStatus

STATE_QUEUED = "queued"
STATE_SCHEDULED = "scheduled"
STATE_WORKING = "working"
STATE_COMPLETED = "completed"
STATE_PASSED_THROUGH = "passed-through"
STATE_FAILED = "failed"
STATE_REJECTED = "rejected"
STATE_CANCELLED = "cancelled"

TERMINAL_STATES: frozenset[str] = frozenset(
    {STATE_COMPLETED, STATE_PASSED_THROUGH, STATE_FAILED, STATE_REJECTED, STATE_CANCELLED}
)

#: Terminal ledger rows older than this are removed with the job-row retention tick.
LEDGER_RETENTION_DAYS = 90


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def remux_dedupe_key(source_key: str, handoff_id: str) -> str:
    """The remux job's key for a hand-off, exactly as intake writes it."""

    return f"{REFINER_FILE_REMUX_PASS_JOB_KIND}:{source_key}:handoff:{handoff_id}"


def find_handoff(session: Session, *, source_key: str, handoff_id: str) -> MediaManagerHandoffRow | None:
    return session.scalars(
        select(MediaManagerHandoffRow).where(
            MediaManagerHandoffRow.source_key == source_key,
            MediaManagerHandoffRow.handoff_id == handoff_id,
        )
    ).first()


def record_handoff_received(
    session: Session,
    *,
    source_key: str,
    handoff_id: str,
    library_id: int | None,
    relative_path: str,
) -> MediaManagerHandoffRow:
    """At intake. A repeat of the same hand-off (the manager retrying it) starts it over."""

    now = datetime.now(UTC)
    row = find_handoff(session, source_key=source_key, handoff_id=handoff_id)
    if row is None:
        row = MediaManagerHandoffRow(
            source_key=source_key,
            handoff_id=handoff_id,
            library_id=library_id,
            relative_path=relative_path,
            state=STATE_QUEUED,
            created_at=now,
            last_changed_at=now,
        )
        session.add(row)
    elif row.state in TERMINAL_STATES:
        row.library_id = library_id
        row.relative_path = relative_path
        row.state = STATE_QUEUED
        row.output_path = None
        row.message = None
        row.last_changed_at = now
    session.flush()
    return row


def record_handoff_outcome(
    session: Session,
    *,
    source_key: str,
    handoff_id: str | None,
    state: str,
    output_path: str | None = None,
    message: str | None = None,
) -> None:
    """A result Weir reached, written when it is reported. Unknown hand-offs are ignored."""

    if not handoff_id:
        return
    row = find_handoff(session, source_key=source_key, handoff_id=handoff_id)
    if row is None or row.state == STATE_CANCELLED:
        return
    if row.state != state or row.output_path != output_path:
        row.state = state
        row.output_path = output_path
        row.message = (message or None) and message[:2000]
        row.last_changed_at = datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class HandoffStatus:
    handoff_id: str
    state: str
    last_changed_at: datetime
    queue_position: int | None = None
    scheduled_for: datetime | None = None
    output_path: str | None = None
    message: str | None = None

    def as_json(self) -> dict[str, object]:
        def iso(value: datetime | None) -> str | None:
            stamped = _utc(value)
            return stamped.isoformat().replace("+00:00", "Z") if stamped is not None else None

        return {
            "handoffId": self.handoff_id,
            "state": self.state,
            "queuePosition": self.queue_position,
            "scheduledFor": iso(self.scheduled_for),
            "lastChangedUtc": iso(self.last_changed_at),
            "outputPath": self.output_path,
            "message": self.message,
        }


def _file_rows(session: Session, row: MediaManagerHandoffRow) -> list[RefinerFileRow]:
    """The file, or every file under the folder, this hand-off covers."""

    if row.library_id is None:
        return []
    path = row.relative_path.rstrip("/")
    return list(
        session.scalars(
            select(RefinerFileRow).where(
                RefinerFileRow.library_id == row.library_id,
                or_(RefinerFileRow.relative_path == path, RefinerFileRow.relative_path.startswith(f"{path}/")),
            )
        )
    )


def _jobs_for(session: Session, row: MediaManagerHandoffRow) -> list[RefinerJob]:
    base = remux_dedupe_key(row.source_key, row.handoff_id)
    conditions = [RefinerJob.dedupe_key == base, RefinerJob.dedupe_key.startswith(f"{base}:")]
    if row.library_id is not None:
        paths = {row.relative_path, *(f.relative_path for f in _file_rows(session, row))}
        for path in paths:
            conditions.append(RefinerJob.dedupe_key == f"{REFINER_FILE_PASS_THROUGH_JOB_KIND}:{row.library_id}:{path}")
            conditions.append(RefinerJob.dedupe_key == f"{REFINER_FILE_REJECT_JOB_KIND}:{row.library_id}:{path}")
    return list(
        session.scalars(
            select(RefinerJob).where(
                or_(*conditions),
                RefinerJob.status.in_([RefinerJobStatus.PENDING.value, RefinerJobStatus.LEASED.value]),
            )
        )
    )


def _queue_position(session: Session, job: RefinerJob) -> int:
    ahead = session.scalar(
        select(func.count(RefinerJob.id)).where(
            RefinerJob.status == RefinerJobStatus.PENDING.value,
            or_(
                RefinerJob.priority > job.priority,
                (RefinerJob.priority == job.priority) & (RefinerJob.id < job.id),
            ),
        )
    )
    return int(ahead or 0) + 1


def _file_state(file_row: RefinerFileRow, now: datetime) -> tuple[str, datetime | None]:
    """One file's state in the manager's words, and when it would next run if that is known."""

    status = file_row.status
    retry_at = _utc(file_row.next_retry_at)
    if status == RefinerFileStatus.PROCESSING.value:
        return STATE_WORKING, None
    if status == RefinerFileStatus.PROCESSED.value:
        return STATE_COMPLETED, None
    if status == RefinerFileStatus.PASSED_THROUGH.value:
        return STATE_PASSED_THROUGH, None
    if status == RefinerFileStatus.REJECTED.value:
        return STATE_REJECTED, None
    if status == RefinerFileStatus.PROCESSING_FAILED.value:
        return (STATE_SCHEDULED, retry_at) if retry_at is not None and retry_at > now else (STATE_FAILED, None)
    if status == RefinerFileStatus.SKIPPED.value:
        # A library rule turned the file away. Nothing will happen to it on its own.
        return STATE_FAILED, None
    if status == RefinerFileStatus.OUT_OF_SCHEDULE.value:
        return STATE_SCHEDULED, None
    if status == RefinerFileStatus.ON_HOLD.value and int(file_row.failure_attempts or 0) >= 3:
        # Quarantined after repeated failures: nothing happens until a person acts. A manager
        # waiting on this would wait for its stall limit, so it is reported as failed.
        return STATE_FAILED, None
    # Waiting, on hold while it settles, library off, or held because the manager is itself
    # mid-import: all "not yet", none of them a stall.
    return STATE_QUEUED, None


def _combine(states: list[str]) -> str:
    """A hand-off covering several files is as far along as its least finished file."""

    for waiting in (STATE_WORKING, STATE_QUEUED, STATE_SCHEDULED):
        if waiting in states:
            return waiting
    for outcome in (STATE_FAILED, STATE_REJECTED, STATE_PASSED_THROUGH):
        if outcome in states:
            return outcome
    return STATE_COMPLETED


def current_status(session: Session, row: MediaManagerHandoffRow) -> HandoffStatus:
    """Work the state out from what exists now, and keep the ledger in step with it."""

    now = datetime.now(UTC)
    live_state: str | None = None
    changed_at: datetime | None = None
    queue_position: int | None = None
    scheduled_for: datetime | None = None
    message: str | None = None

    if row.state != STATE_CANCELLED:
        jobs = _jobs_for(session, row)
        files = _file_rows(session, row)
        states: list[str] = []
        stamps: list[datetime] = []
        busy_paths: set[str] = set()

        for job in jobs:
            stamp = _utc(job.updated_at)
            if stamp is not None:
                stamps.append(stamp)
            with contextlib.suppress(ValueError):
                busy_paths.add(str(json.loads(job.payload_json or "{}").get("relative_media_path") or ""))
            if job.status == RefinerJobStatus.LEASED.value:
                states.append(STATE_WORKING)
                continue
            not_before = _utc(job.not_before)
            if not_before is not None and not_before > now:
                states.append(STATE_SCHEDULED)
                scheduled_for = min(scheduled_for, not_before) if scheduled_for else not_before
            else:
                states.append(STATE_QUEUED)
                position = _queue_position(session, job)
                queue_position = min(queue_position, position) if queue_position else position

        for file_row in files:
            stamp = _utc(file_row.updated_at)
            if stamp is not None:
                stamps.append(stamp)
            if file_row.relative_path in busy_paths:
                # A queued or running job speaks for this file more recently than its row does.
                if file_row.status_reason and message is None:
                    message = file_row.status_reason
                continue
            state, when = _file_state(file_row, now)
            states.append(state)
            if when is not None:
                scheduled_for = min(scheduled_for, when) if scheduled_for else when
            if file_row.status_reason and (message is None or state not in TERMINAL_STATES):
                message = file_row.status_reason

        if states:
            live_state = _combine(states)
            changed_at = max(stamps) if stamps else None
            if live_state != STATE_QUEUED:
                queue_position = None
            if live_state != STATE_SCHEDULED:
                scheduled_for = None

    if live_state is not None:
        previous = _utc(row.last_changed_at)
        if live_state != row.state:
            row.state = live_state
            # When the change happened if that is known and newer, otherwise now: never backwards.
            row.last_changed_at = (
                changed_at if changed_at is not None and (previous is None or changed_at > previous) else now
            )
        elif changed_at is not None and previous is not None and changed_at > previous:
            # Same state, but something real happened (a new attempt, a retry scheduled).
            row.last_changed_at = changed_at
        if message is not None and live_state not in TERMINAL_STATES:
            row.message = message[:2000]

    return HandoffStatus(
        handoff_id=row.handoff_id,
        state=row.state,
        last_changed_at=_utc(row.last_changed_at) or now,
        queue_position=queue_position,
        scheduled_for=scheduled_for,
        output_path=row.output_path if row.state in {STATE_COMPLETED, STATE_PASSED_THROUGH} else None,
        message=message if message is not None else row.message,
    )


def cancel_handoff(session: Session, row: MediaManagerHandoffRow) -> tuple[bool, str]:
    """Drop a hand-off that has not started. Never touches a file; never stops running work.

    Returns ``(cancelled, sentence)``. A hand-off already working or finished is refused.
    """

    status = current_status(session, row)
    if status.state not in {STATE_QUEUED, STATE_SCHEDULED}:
        return False, f"This hand-off is {status.state}, so Weir did not cancel it."
    for job in _jobs_for(session, row):
        if job.status == RefinerJobStatus.PENDING.value:
            cancel_pending_refiner_job(session, job_id=job.id)
    for file_row in _file_rows(session, row):
        if file_row.next_retry_at is not None:
            file_row.next_retry_at = None
    row.state = STATE_CANCELLED
    row.message = "The media manager cancelled this hand-off before Weir started on it."
    row.last_changed_at = datetime.now(UTC)
    session.flush()
    return True, row.message


def prune_ledger(session: Session, *, now: datetime | None = None) -> int:
    cutoff = (now or datetime.now(UTC)) - timedelta(days=LEDGER_RETENTION_DAYS)
    result = session.execute(
        delete(MediaManagerHandoffRow).where(
            MediaManagerHandoffRow.state.in_(sorted(TERMINAL_STATES)),
            MediaManagerHandoffRow.last_changed_at < cutoff,
        )
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]
