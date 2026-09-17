"""What a worker says when a job fails, used by the Refiner workers (#488).

Three rules from ``docs/operator-messaging-standard.md`` meet here:

- **The words match what happens next.** A failed attempt is put back in the queue until it has
  used its attempts (``fail_claimed_*_job``), so "marked failed" is only said when it is true.
- **Operator text carries no queue kinds or raw exceptions.** Those go in a technical part of
  ``last_error``, after the sentence a person reads.
- **One failure, one Activity entry.** A handler that already recorded its own failure raises
  :class:`AlreadyRecordedFailure`, and the worker does not write a second one.
"""

from __future__ import annotations

from mediamop.platform.observability.failure_messages import OperatorFailure, operator_failure_from_exception

_ERROR_LIMIT = 10_000


class AlreadyRecordedFailure(RuntimeError):
    """The handler already wrote this failure to Activity; the worker still fails the job."""


def retry_coming(*, attempt_count: int, max_attempts: int) -> bool:
    return int(attempt_count) < int(max_attempts)


def job_failure(*, module: str, exc: BaseException, will_retry: bool) -> OperatorFailure:
    return operator_failure_from_exception(
        module=module,
        action="job",
        exc=exc,
        continuation=(
            "MediaMop will try this job again shortly."
            if will_retry
            else "This job is marked failed so it does not look successful."
        ),
    )


def stored_error(failure: OperatorFailure) -> str:
    """The sentence a person reads first, then what to do, then the technical detail."""

    text = failure.message
    if failure.next_action:
        text += f" Next action: {failure.next_action}"
    if failure.technical_detail:
        text += f" Technical detail: {failure.technical_detail}"
    return text[:_ERROR_LIMIT]


def refused_job_error(*, module: str, technical_reason: str, will_retry: bool) -> str:
    """A job this worker cannot run, e.g. one queued for another part of MediaMop."""

    return stored_error(job_failure(module=module, exc=RuntimeError(technical_reason), will_retry=will_retry))
