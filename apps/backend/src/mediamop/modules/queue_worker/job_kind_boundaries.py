"""Module-owned durable queue lanes: reserved ``job_kind`` prefixes (SQLite, one writer per table).

Each module keeps its own persisted jobs table and worker pool. ``job_kind`` strings are
function-named *inside* that module's namespace (prefix = module lane).

See ``docs/adr/ADR-0007-module-owned-worker-lanes.md``. Operator timing contracts (intervals,
schedules, cooldowns, retries, last-run, pruning horizons) must not cross job families; see
``docs/adr/ADR-0009-suite-wide-timing-isolation.md``.
"""

from __future__ import annotations

from collections.abc import Mapping

# --- Refiner lane (`refiner_jobs`): Refiner-owned durable work -----------------------------------
REFINER_QUEUE_JOB_KIND_PREFIX = "refiner."

# --- Pruner sibling lane (reserved on sibling queues) --------------------------------------------
PRUNER_QUEUE_JOB_KIND_PREFIX = "pruner."

# Legacy Trimmer lane prefix — no longer a valid lane; rejected on every queue (abandoned prefix).
LEGACY_TRIMMER_QUEUE_JOB_KIND_PREFIX = "trimmer."

# Subber moved to Deluno, which owns the library it needed. Its prefix joins Trimmer's as
# abandoned rather than simply disappearing: a queue row left over from an older install
# must still be refused by every lane, not quietly accepted by whichever one it lands on.
LEGACY_SUBBER_QUEUE_JOB_KIND_PREFIX = "subber."

# Refiner's supplied-payload evaluation lane, removed in #339. On a schedule it was
# enqueued with no payload at all, so it evaluated zero rows and wrote the same constant
# — ``row_count: 0, owned: false, blocked_upstream: false`` — once per interval forever.
# Its scheduled mode was not a feature that happened to be off; it was provably
# meaningless. The domain functions it exercised are covered directly by tests and stay
# where they are.
#
# The prefix is retired rather than simply disappearing, for the same reason Trimmer's
# and Subber's are: a row left by an older install must still be refused, not quietly
# accepted by a worker that no longer knows what it is.
LEGACY_REFINER_SUPPLIED_PAYLOAD_EVALUATION_JOB_KIND_PREFIX = "refiner.supplied_payload_evaluation."

# Refiner's candidate gate, reshaped in #339. It was a queued family with no scheduler and
# no UI calling it: an operator asked "is this file held?" and got a job id back, then had
# to find the answer in the activity feed. It is a read-only question whose answer the
# caller wants immediately, so it became a synchronous endpoint and the queue round-trip
# went away. The evaluator itself is unchanged and still in use.
LEGACY_REFINER_CANDIDATE_GATE_JOB_KIND_PREFIX = "refiner.candidate_gate."


def _legacy_or_foreign_prefixes() -> tuple[str, ...]:
    return (
        LEGACY_TRIMMER_QUEUE_JOB_KIND_PREFIX,
        LEGACY_SUBBER_QUEUE_JOB_KIND_PREFIX,
        LEGACY_REFINER_SUPPLIED_PAYLOAD_EVALUATION_JOB_KIND_PREFIX,
        LEGACY_REFINER_CANDIDATE_GATE_JOB_KIND_PREFIX,
    )


# Prefixes that must never be enqueued or executed on ``refiner_jobs`` / Refiner workers.
_FORBIDDEN_ON_REFINER_LANE: tuple[str, ...] = (
    PRUNER_QUEUE_JOB_KIND_PREFIX,
    *_legacy_or_foreign_prefixes(),
)


def job_kind_forbidden_on_refiner_lane(job_kind: str) -> bool:
    """True when ``job_kind`` is reserved for another module's table."""

    return any(job_kind.startswith(p) for p in _FORBIDDEN_ON_REFINER_LANE)


def validate_refiner_enqueue_job_kind(job_kind: str) -> None:
    """Refiner queue rows must use the Refiner lane only (not the Pruner namespace)."""

    if job_kind_forbidden_on_refiner_lane(job_kind):
        msg = (
            "refiner_enqueue_or_get_job refuses job_kind reserved for another module lane "
            f"(got {job_kind!r}); use that module's table + enqueue function"
        )
        raise ValueError(msg)
    if not job_kind.startswith(REFINER_QUEUE_JOB_KIND_PREFIX):
        msg = (
            "refiner_enqueue_or_get_job requires job_kind to start with "
            f"{REFINER_QUEUE_JOB_KIND_PREFIX!r} (got {job_kind!r}); production durable Refiner "
            "families use refiner.* kinds on refiner_jobs only"
        )
        raise ValueError(msg)


def validate_refiner_worker_handler_registry(
    job_handlers: Mapping[str, object],
) -> None:
    """Refiner workers must register handlers only under the ``refiner.*`` namespace."""

    bad = sorted(
        {
            k
            for k in job_handlers
            if job_kind_forbidden_on_refiner_lane(k) or not k.startswith(REFINER_QUEUE_JOB_KIND_PREFIX)
        },
    )
    if bad:
        msg = (
            "Refiner worker handler registry keys must start with "
            f"{REFINER_QUEUE_JOB_KIND_PREFIX!r} and must not use another module's reserved "
            f"prefixes (offending keys: {bad!r})"
        )
        raise ValueError(msg)


# Prefixes that must never be enqueued or executed on ``pruner_jobs`` / Pruner workers.
_FORBIDDEN_ON_PRUNER_LANE: tuple[str, ...] = (
    REFINER_QUEUE_JOB_KIND_PREFIX,
    *_legacy_or_foreign_prefixes(),
)


def job_kind_forbidden_on_pruner_lane(job_kind: str) -> bool:
    """True when ``job_kind`` is reserved for another module's table or lane."""

    return any(job_kind.startswith(p) for p in _FORBIDDEN_ON_PRUNER_LANE)


def validate_pruner_enqueue_job_kind(job_kind: str) -> None:
    """Pruner queue rows must use the Pruner lane only (not the Refiner namespace)."""

    if job_kind_forbidden_on_pruner_lane(job_kind):
        msg = (
            "pruner_enqueue_or_get_job refuses job_kind reserved for another module lane "
            f"(got {job_kind!r}); use that module's table + enqueue function"
        )
        raise ValueError(msg)
    if not job_kind.startswith(PRUNER_QUEUE_JOB_KIND_PREFIX):
        msg = (
            "pruner_enqueue_or_get_job requires job_kind to start with "
            f"{PRUNER_QUEUE_JOB_KIND_PREFIX!r} (got {job_kind!r}); production durable Pruner "
            "families use pruner.* kinds on pruner_jobs only"
        )
        raise ValueError(msg)


def validate_pruner_worker_handler_registry(
    job_handlers: Mapping[str, object],
) -> None:
    """Pruner workers must register handlers only under the ``pruner.*`` namespace."""

    bad = sorted(
        {
            k
            for k in job_handlers
            if job_kind_forbidden_on_pruner_lane(k) or not k.startswith(PRUNER_QUEUE_JOB_KIND_PREFIX)
        },
    )
    if bad:
        msg = (
            "Pruner worker handler registry keys must start with "
            f"{PRUNER_QUEUE_JOB_KIND_PREFIX!r} and must not use another module's reserved "
            f"prefixes (offending keys: {bad!r})"
        )
        raise ValueError(msg)
