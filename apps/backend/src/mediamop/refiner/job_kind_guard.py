"""Which ``job_kind`` strings may sit in ``refiner_jobs`` and be run by its workers.

Every durable job is a ``refiner.*`` kind. Retired prefixes are listed by name rather than
simply disappearing, so a queue row left by an older install is refused instead of being
claimed by a worker that no longer knows what it is.

This used to be a boundary between module-owned queue lanes (``docs/adr/ADR-0007``). With
one application there is one lane, so the only part left is the refusal of retired kinds.
Operator timing contracts still must not cross job families; see
``docs/adr/ADR-0009-suite-wide-timing-isolation.md``.
"""

from __future__ import annotations

from collections.abc import Mapping

JOB_KIND_PREFIX = "refiner."

# Trimmer was removed long ago; its rows are refused.
RETIRED_TRIMMER_JOB_KIND_PREFIX = "trimmer."

# Subber moved to Deluno, which owns the library it needed.
RETIRED_SUBBER_JOB_KIND_PREFIX = "subber."

# Pruner moved to Deluno too (#473).
RETIRED_PRUNER_JOB_KIND_PREFIX = "pruner."

# Refiner's supplied-payload evaluation family, removed in #339. On a schedule it was
# enqueued with no payload at all, so it evaluated zero rows and wrote the same constant
# — ``row_count: 0, owned: false, blocked_upstream: false`` — once per interval forever.
# Its scheduled mode was not a feature that happened to be off; it was provably
# meaningless. The domain functions it exercised are covered directly by tests and stay
# where they are.
RETIRED_SUPPLIED_PAYLOAD_EVALUATION_JOB_KIND_PREFIX = "refiner.supplied_payload_evaluation."

# Refiner's candidate gate, reshaped in #339. It was a queued family with no scheduler and
# no UI calling it: an operator asked "is this file held?" and got a job id back, then had
# to find the answer in the activity feed. It is a read-only question whose answer the
# caller wants immediately, so it became a synchronous endpoint and the queue round-trip
# went away. The evaluator itself is unchanged and still in use.
RETIRED_CANDIDATE_GATE_JOB_KIND_PREFIX = "refiner.candidate_gate."

RETIRED_JOB_KIND_PREFIXES: tuple[str, ...] = (
    RETIRED_TRIMMER_JOB_KIND_PREFIX,
    RETIRED_SUBBER_JOB_KIND_PREFIX,
    RETIRED_PRUNER_JOB_KIND_PREFIX,
    RETIRED_SUPPLIED_PAYLOAD_EVALUATION_JOB_KIND_PREFIX,
    RETIRED_CANDIDATE_GATE_JOB_KIND_PREFIX,
)


def job_kind_is_retired(job_kind: str) -> bool:
    """True when ``job_kind`` belongs to a retired family and must never run."""

    return any(job_kind.startswith(p) for p in RETIRED_JOB_KIND_PREFIXES)


def validate_refiner_enqueue_job_kind(job_kind: str) -> None:
    """Queue rows must be live ``refiner.*`` kinds."""

    if job_kind_is_retired(job_kind):
        msg = f"refiner_enqueue_or_get_job refuses a retired job_kind (got {job_kind!r})"
        raise ValueError(msg)
    if not job_kind.startswith(JOB_KIND_PREFIX):
        msg = f"refiner_enqueue_or_get_job requires job_kind to start with {JOB_KIND_PREFIX!r} (got {job_kind!r})"
        raise ValueError(msg)


def validate_refiner_worker_handler_registry(
    job_handlers: Mapping[str, object],
) -> None:
    """Workers may register handlers only for live ``refiner.*`` kinds."""

    bad = sorted({k for k in job_handlers if job_kind_is_retired(k) or not k.startswith(JOB_KIND_PREFIX)})
    if bad:
        msg = (
            "Refiner worker handler registry keys must start with "
            f"{JOB_KIND_PREFIX!r} and must not use a retired prefix (offending keys: {bad!r})"
        )
        raise ValueError(msg)
