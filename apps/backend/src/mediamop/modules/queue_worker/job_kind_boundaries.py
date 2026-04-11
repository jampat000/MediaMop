"""Module-owned durable queue lanes: reserved ``job_kind`` prefixes (SQLite, one writer per table).

Each module keeps its own persisted jobs table and worker pool. ``job_kind`` strings are
function-named *inside* that module's namespace (prefix = module lane).

See ``docs/adr/0007-module-owned-worker-lanes.md``.
"""

from __future__ import annotations

from collections.abc import Mapping

# --- Fetcher lane (`fetcher_jobs`): function families owned by Fetcher ---------------------------
FETCHER_QUEUE_JOB_KIND_PREFIXES: tuple[str, ...] = (
    "failed_import.",
    "missing_search.",
    "upgrade_search.",
)

# --- Refiner lane (`refiner_jobs`): Refiner-owned durable work -----------------------------------
REFINER_QUEUE_JOB_KIND_PREFIX = "refiner."

# --- Future module lanes (reserved on sibling queues; must never appear on Refiner/Fetcher) -----
TRIMMER_QUEUE_JOB_KIND_PREFIX = "trimmer."
SUBBER_QUEUE_JOB_KIND_PREFIX = "subber."

# Prefixes that must never be enqueued or executed on ``refiner_jobs`` / Refiner workers.
_FORBIDDEN_ON_REFINER_LANE: tuple[str, ...] = (
    *FETCHER_QUEUE_JOB_KIND_PREFIXES,
    TRIMMER_QUEUE_JOB_KIND_PREFIX,
    SUBBER_QUEUE_JOB_KIND_PREFIX,
)

# Prefixes that must never be enqueued on ``fetcher_jobs`` (other modules' lanes).
_FORBIDDEN_ON_FETCHER_ENQUEUE_PREFIXES: tuple[str, ...] = (
    REFINER_QUEUE_JOB_KIND_PREFIX,
    TRIMMER_QUEUE_JOB_KIND_PREFIX,
    SUBBER_QUEUE_JOB_KIND_PREFIX,
)

# Prefixes that must never run on Fetcher workers (mis-placed rows); tests may use unprefixed kinds.
_FORBIDDEN_ON_FETCHER_WORKER_PREFIXES: tuple[str, ...] = (
    REFINER_QUEUE_JOB_KIND_PREFIX,
    TRIMMER_QUEUE_JOB_KIND_PREFIX,
    SUBBER_QUEUE_JOB_KIND_PREFIX,
)


def job_kind_is_fetcher_failed_import_namespace(job_kind: str) -> bool:
    """True for the failed-import family on the Fetcher lane (subset of :data:`FETCHER_QUEUE_JOB_KIND_PREFIXES`)."""

    return job_kind.startswith(FETCHER_QUEUE_JOB_KIND_PREFIXES[0])


def job_kind_allowed_fetcher_queue_prefix(job_kind: str) -> bool:
    """Whether ``job_kind`` belongs to the Fetcher durable lane (handler registry / product work)."""

    return any(job_kind.startswith(p) for p in FETCHER_QUEUE_JOB_KIND_PREFIXES)


def job_kind_forbidden_on_refiner_lane(job_kind: str) -> bool:
    """True when ``job_kind`` is reserved for another module's table or the Fetcher lane."""

    return any(job_kind.startswith(p) for p in _FORBIDDEN_ON_REFINER_LANE)


def job_kind_forbidden_on_fetcher_enqueue(job_kind: str) -> bool:
    """``fetcher_enqueue_or_get_job`` must not accept other modules' reserved prefixes."""

    return any(job_kind.startswith(p) for p in _FORBIDDEN_ON_FETCHER_ENQUEUE_PREFIXES)


def job_kind_forbidden_on_fetcher_worker(job_kind: str) -> bool:
    """Fetcher workers must not execute rows stamped with another module's lane prefix."""

    return any(job_kind.startswith(p) for p in _FORBIDDEN_ON_FETCHER_WORKER_PREFIXES)


def validate_refiner_enqueue_job_kind(job_kind: str) -> None:
    """Refiner queue rows must use the Refiner lane only (not Fetcher/Trimmer/Subber namespaces)."""

    if job_kind_forbidden_on_refiner_lane(job_kind):
        msg = (
            "refiner_enqueue_or_get_job refuses job_kind reserved for another module lane "
            f"(got {job_kind!r}); use that module's table + enqueue function"
        )
        raise ValueError(msg)


def validate_refiner_worker_handler_registry(
    job_handlers: Mapping[str, object],
) -> None:
    """Refiner workers must not register handlers for another module's ``job_kind`` prefixes."""

    bad = [k for k in job_handlers if job_kind_forbidden_on_refiner_lane(k)]
    if bad:
        msg = (
            "Refiner worker handler registry must not include non-Refiner lane job_kind keys "
            f"(offending keys: {bad!r})"
        )
        raise ValueError(msg)


def validate_fetcher_enqueue_job_kind(job_kind: str) -> None:
    """``fetcher_jobs`` rows must not use Refiner/Trimmer/Subber reserved prefixes."""

    if job_kind_forbidden_on_fetcher_enqueue(job_kind):
        msg = (
            "fetcher_enqueue_or_get_job refuses job_kind reserved for another module lane "
            f"(got {job_kind!r})"
        )
        raise ValueError(msg)


def validate_fetcher_worker_handler_registry_keys(
    job_handlers: Mapping[str, object],
) -> None:
    """Fetcher worker handler keys must use a Fetcher lane prefix (function-named inside Fetcher)."""

    bad = [k for k in job_handlers if not job_kind_allowed_fetcher_queue_prefix(k)]
    if bad:
        msg = (
            "Fetcher worker handler registry keys must start with one of "
            f"{FETCHER_QUEUE_JOB_KIND_PREFIXES!r} (offending keys: {bad!r})"
        )
        raise ValueError(msg)
