"""A small vocabulary for *why* a file failed, so retry can be a policy rather than a guess.

Failure reasons were free text. That is fine for a person reading one row and useless for
anything that has to decide: "retry this" and "never retry this" are completely different
answers, and a substring match against a sentence is not a way to tell them apart.

Refiner already distinguished the two moments — ``failed_before_execution`` and
``failed_during_execution`` — but nothing acted on the distinction. It matters:

- A file with no retainable audio track will still have no retainable audio track in five
  minutes. Retrying it burns a worker slot to reach the same conclusion.
- An ffmpeg process that died, a disk that filled, a network share that dropped — those
  are the same file meeting a different world, and retrying is exactly right.

So the default policy retries execution failures and does not retry preflight ones. Both
are per-library settings, because an operator watching a flaky NAS will want different
answers from one running on local disk.
"""

from __future__ import annotations

from enum import StrEnum

from mediamop.modules.refiner.file_remux_pass.visibility import (
    REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION,
    REMUX_PASS_OUTCOME_FAILED_DURING_EXECUTION,
)


class RefinerFailureClass(StrEnum):
    """Why a file failed, in the terms a retry policy can act on."""

    #: The file was rejected before any work started — unsupported, unreadable, no
    #: retainable audio, gates unmet. Retrying reaches the same conclusion.
    PREFLIGHT = "preflight"
    #: Work started and the process failed — ffmpeg died, the disk filled, a share
    #: dropped. The same file meeting a different world; retrying is reasonable.
    EXECUTION = "execution"
    #: A guardrail deliberately stopped the file. Never retried automatically: the
    #: guardrail is the answer, not an obstacle to route around.
    GUARDRAIL = "guardrail"
    #: Something MediaMop could not attribute. Treated as terminal, because retrying an
    #: unclassified failure forever is how a queue fills with work nobody understands.
    UNKNOWN = "unknown"


_BY_OUTCOME: dict[str, RefinerFailureClass] = {
    REMUX_PASS_OUTCOME_FAILED_BEFORE_EXECUTION: RefinerFailureClass.PREFLIGHT,
    REMUX_PASS_OUTCOME_FAILED_DURING_EXECUTION: RefinerFailureClass.EXECUTION,
    "skipped_guardrail": RefinerFailureClass.GUARDRAIL,
}


def classify_failure(outcome: str | None) -> RefinerFailureClass:
    """Map a remux-pass outcome onto the retry vocabulary."""

    return _BY_OUTCOME.get((outcome or "").strip().lower(), RefinerFailureClass.UNKNOWN)


def is_retryable(
    failure_class: RefinerFailureClass | str,
    *,
    retry_preflight_failures: bool,
    retry_execution_failures: bool,
) -> bool:
    """Whether this class of failure may be retried under the library's policy.

    Guardrail and unknown are never retryable and are not offered as settings. A
    guardrail firing is the answer; an unclassified failure retried on a timer is how a
    queue fills with work nobody has looked at.
    """

    value = (
        failure_class.value if isinstance(failure_class, RefinerFailureClass) else str(failure_class).strip().lower()
    )
    if value == RefinerFailureClass.PREFLIGHT.value:
        return bool(retry_preflight_failures)
    if value == RefinerFailureClass.EXECUTION.value:
        return bool(retry_execution_failures)
    return False


def backoff_seconds_for_attempt(*, attempt: int, base_seconds: int) -> int:
    """Delay before attempt number ``attempt`` (1-based), doubling and capped at an hour.

    Doubling rather than a fixed wait, because the failures worth retrying are usually
    the ones that need time — a share coming back, a disk being cleared — and hammering
    a broken thing every five minutes helps nobody. Capped so a long-lived queue does not
    quietly schedule a retry for next week.
    """

    base = max(1, int(base_seconds))
    exponent = max(0, int(attempt) - 1)
    return min(3600, base * (2**exponent)) if exponent < 16 else 3600
