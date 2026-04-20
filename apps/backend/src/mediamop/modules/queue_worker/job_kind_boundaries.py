"""Module-owned durable queue lanes: reserved ``job_kind`` prefixes (SQLite, one writer per table).

Each module keeps its own persisted jobs table and worker pool. ``job_kind`` strings are
function-named *inside* that module's namespace (prefix = module lane).

See ``docs/adr/ADR-0007-module-owned-worker-lanes.md``. Operator timing contracts (intervals,
schedules, cooldowns, retries, last-run, pruning horizons) must not cross job families; see
``docs/adr/ADR-0009-suite-wide-timing-isolation.md``.
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

# --- Pruner / Subber sibling lanes (reserved on sibling queues; must never appear on Fetcher/Refiner) ---
PRUNER_QUEUE_JOB_KIND_PREFIX = "pruner."
SUBBER_QUEUE_JOB_KIND_PREFIX = "subber."
BROKER_QUEUE_JOB_KIND_PREFIX = "broker."

# Legacy Trimmer lane prefix — no longer a valid lane; rejected on every queue (abandoned prefix).
LEGACY_TRIMMER_QUEUE_JOB_KIND_PREFIX = "trimmer."


def _legacy_or_foreign_prefixes() -> tuple[str, ...]:
    return (LEGACY_TRIMMER_QUEUE_JOB_KIND_PREFIX,)


# Prefixes that must never be enqueued or executed on ``refiner_jobs`` / Refiner workers.
_FORBIDDEN_ON_REFINER_LANE: tuple[str, ...] = (
    *FETCHER_QUEUE_JOB_KIND_PREFIXES,
    PRUNER_QUEUE_JOB_KIND_PREFIX,
    SUBBER_QUEUE_JOB_KIND_PREFIX,
    BROKER_QUEUE_JOB_KIND_PREFIX,
    *_legacy_or_foreign_prefixes(),
)

# Prefixes that must never be enqueued on ``fetcher_jobs`` (other modules' lanes).
_FORBIDDEN_ON_FETCHER_ENQUEUE_PREFIXES: tuple[str, ...] = (
    REFINER_QUEUE_JOB_KIND_PREFIX,
    PRUNER_QUEUE_JOB_KIND_PREFIX,
    SUBBER_QUEUE_JOB_KIND_PREFIX,
    BROKER_QUEUE_JOB_KIND_PREFIX,
    *_legacy_or_foreign_prefixes(),
)

# Prefixes that must never run on Fetcher workers (mis-placed rows); tests may use unprefixed kinds.
_FORBIDDEN_ON_FETCHER_WORKER_PREFIXES: tuple[str, ...] = (
    REFINER_QUEUE_JOB_KIND_PREFIX,
    PRUNER_QUEUE_JOB_KIND_PREFIX,
    SUBBER_QUEUE_JOB_KIND_PREFIX,
    BROKER_QUEUE_JOB_KIND_PREFIX,
    *_legacy_or_foreign_prefixes(),
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
    """Refiner queue rows must use the Refiner lane only (not Fetcher/Pruner/Subber namespaces)."""

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


def validate_fetcher_enqueue_job_kind(job_kind: str) -> None:
    """``fetcher_jobs`` rows must not use Refiner/Pruner/Subber reserved prefixes."""

    if job_kind_forbidden_on_fetcher_enqueue(job_kind):
        msg = (
            "fetcher_enqueue_or_get_job refuses job_kind reserved for another module lane "
            f"(got {job_kind!r})"
        )
        raise ValueError(msg)


# Prefixes that must never be enqueued or executed on ``pruner_jobs`` / Pruner workers.
_FORBIDDEN_ON_PRUNER_LANE: tuple[str, ...] = (
    *FETCHER_QUEUE_JOB_KIND_PREFIXES,
    REFINER_QUEUE_JOB_KIND_PREFIX,
    SUBBER_QUEUE_JOB_KIND_PREFIX,
    BROKER_QUEUE_JOB_KIND_PREFIX,
    *_legacy_or_foreign_prefixes(),
)


def job_kind_forbidden_on_pruner_lane(job_kind: str) -> bool:
    """True when ``job_kind`` is reserved for another module's table or lane."""

    return any(job_kind.startswith(p) for p in _FORBIDDEN_ON_PRUNER_LANE)


def validate_pruner_enqueue_job_kind(job_kind: str) -> None:
    """Pruner queue rows must use the Pruner lane only (not Fetcher/Refiner/Subber namespaces)."""

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


# Prefixes that must never be enqueued or executed on ``subber_jobs`` / Subber workers.
_FORBIDDEN_ON_SUBBER_LANE: tuple[str, ...] = (
    *FETCHER_QUEUE_JOB_KIND_PREFIXES,
    REFINER_QUEUE_JOB_KIND_PREFIX,
    PRUNER_QUEUE_JOB_KIND_PREFIX,
    BROKER_QUEUE_JOB_KIND_PREFIX,
    *_legacy_or_foreign_prefixes(),
)


def job_kind_forbidden_on_subber_lane(job_kind: str) -> bool:
    """True when ``job_kind`` is reserved for another module's table or lane."""

    return any(job_kind.startswith(p) for p in _FORBIDDEN_ON_SUBBER_LANE)


def validate_subber_enqueue_job_kind(job_kind: str) -> None:
    """Subber queue rows must use the Subber lane only (not Fetcher/Refiner/Pruner namespaces)."""

    if job_kind_forbidden_on_subber_lane(job_kind):
        msg = (
            "subber_enqueue_or_get_job refuses job_kind reserved for another module lane "
            f"(got {job_kind!r}); use that module's table + enqueue function"
        )
        raise ValueError(msg)
    if not job_kind.startswith(SUBBER_QUEUE_JOB_KIND_PREFIX):
        msg = (
            "subber_enqueue_or_get_job requires job_kind to start with "
            f"{SUBBER_QUEUE_JOB_KIND_PREFIX!r} (got {job_kind!r}); production durable Subber "
            "families use subber.* kinds on subber_jobs only"
        )
        raise ValueError(msg)


def validate_subber_worker_handler_registry(
    job_handlers: Mapping[str, object],
) -> None:
    """Subber workers must register handlers only under the ``subber.*`` namespace."""

    bad = sorted(
        {
            k
            for k in job_handlers
            if job_kind_forbidden_on_subber_lane(k) or not k.startswith(SUBBER_QUEUE_JOB_KIND_PREFIX)
        },
    )
    if bad:
        msg = (
            "Subber worker handler registry keys must start with "
            f"{SUBBER_QUEUE_JOB_KIND_PREFIX!r} and must not use another module's reserved "
            f"prefixes (offending keys: {bad!r})"
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


# Prefixes that must never be enqueued or executed on ``broker_jobs`` / Broker workers.
_FORBIDDEN_ON_BROKER_LANE: tuple[str, ...] = (
    *FETCHER_QUEUE_JOB_KIND_PREFIXES,
    REFINER_QUEUE_JOB_KIND_PREFIX,
    PRUNER_QUEUE_JOB_KIND_PREFIX,
    SUBBER_QUEUE_JOB_KIND_PREFIX,
    *_legacy_or_foreign_prefixes(),
)


def job_kind_forbidden_on_broker_lane(job_kind: str) -> bool:
    """True when ``job_kind`` is reserved for another module's table or lane."""

    return any(job_kind.startswith(p) for p in _FORBIDDEN_ON_BROKER_LANE)


def validate_broker_enqueue_job_kind(job_kind: str) -> None:
    """Broker queue rows must use the Broker lane only (not Fetcher/Refiner/Pruner/Subber namespaces)."""

    if job_kind_forbidden_on_broker_lane(job_kind):
        msg = (
            "broker_enqueue_or_get_job refuses job_kind reserved for another module lane "
            f"(got {job_kind!r}); use that module's table + enqueue function"
        )
        raise ValueError(msg)
    if not job_kind.startswith(BROKER_QUEUE_JOB_KIND_PREFIX):
        msg = (
            "broker_enqueue_or_get_job requires job_kind to start with "
            f"{BROKER_QUEUE_JOB_KIND_PREFIX!r} (got {job_kind!r}); production durable Broker "
            "families use broker.* kinds on broker_jobs only"
        )
        raise ValueError(msg)


def validate_broker_worker_handler_registry(
    job_handlers: Mapping[str, object],
) -> None:
    """Broker workers must register handlers only under the ``broker.*`` namespace."""

    bad = sorted(
        {
            k
            for k in job_handlers
            if job_kind_forbidden_on_broker_lane(k) or not k.startswith(BROKER_QUEUE_JOB_KIND_PREFIX)
        },
    )
    if bad:
        msg = (
            "Broker worker handler registry keys must start with "
            f"{BROKER_QUEUE_JOB_KIND_PREFIX!r} and must not use another module's reserved "
            f"prefixes (offending keys: {bad!r})"
        )
        raise ValueError(msg)
