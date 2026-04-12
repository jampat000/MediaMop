# ADR-0009: Suite-wide timing isolation for durable work

## Status

Accepted — **hard rule** for Fetcher, Refiner, Trimmer, and Subber.

## Context

Operators configure **when** and **how often** background work may run: intervals, schedule windows, cooldowns, retries, and visibility into last completion. If two unrelated job families share one timer, one cooldown bucket, or one pruning rule driven by the other family’s delay, one lane **blocks or suppresses** the other. That violates the operator contract.

Module-owned tables and workers (ADR-0007) are necessary but not sufficient: **timing contracts must also be owned** at module boundary first, then **per scheduled job family** inside the module.

## Decision

### Standard (non-negotiable)

1. **Separate by module first.** No timing contract defined for module A may be stored, read, or advanced on behalf of module B. No shared row, column, env var, or in-memory timer substitutes for that split (except purely **process-internal** mechanics listed under “Out of scope” below).

2. **Separate by job family inside the module.** Any distinct user-facing durable job family (distinct `job_kind` contract or distinct product “lane”) has **its own** timing surface: its own interval and/or schedule window, its own retry/cooldown semantics, its own last-run persistence (when last-run is a product signal), and its own pruning window when pruning is derived from retry/cooldown minutes.

3. **No hidden global timing** that causes one job family to wait on another’s eligibility. Cooldown keys, schedule checks, and persisted “last run” fields must not collapse multiple families into one bucket.

### What counts as a timing contract

These require per-family (and per-module) isolation when operators set expectations:

- **Interval** between enqueue ticks or between worker-driven passes tied to a family.
- **Schedule window** (wall-clock / timezone gate before work runs).
- **Cooldown** between repeated actions on the same logical item for that family.
- **Retry delay** (minimum time before re-attempting the same item or pass for that family).
- **Last-run tracking** when persisted for operator or automation summaries **per family**.
- **Pruning** of durable audit or cooldown rows when the cutoff is computed from another family’s delay (forbidden: one family’s delay must not set the prune horizon for another family’s rows).

### Worker count and leases

- **`MEDIAMOP_FETCHER_WORKER_COUNT`**, **`MEDIAMOP_REFINER_WORKER_COUNT`**, **`MEDIAMOP_TRIMMER_WORKER_COUNT`**, and **`MEDIAMOP_SUBBER_WORKER_COUNT`** control **throughput and claim ordering** on their respective lanes. They do **not** replace per-family intervals, cooldowns, or schedules. Increasing worker count must not be the only knob that “fixes” one family waiting on another.

### Process-internal mechanics (out of scope for “shared contracts”)

Fixed short backoffs after **enqueue I/O errors**, worker **idle sleep** between claim attempts, and **lease TTL** on claimed rows are infrastructure stability knobs. They are **not** operator-configured timing contracts and may remain global **within that worker pool**. They must **not** implement product cooldown or replace per-family schedule logic.

### Examples (Fetcher)

These are **four** independent timing contracts today:

- Missing TV (`missing_search.sonarr.*`): own settings, cooldown rows keyed `(sonarr, missing, episode, id)`, own last-run column, own enqueue interval, own schedule window env keys, own prune branch in `prune_fetcher_arr_action_log`.
- Missing movies (`missing_search.radarr.*`): same pattern for `(radarr, missing, movie, id)`.
- Upgrade TV (`upgrade_search.sonarr.*`): `(sonarr, upgrade, episode, id)`.
- Upgrade movies (`upgrade_search.radarr.*`): `(radarr, upgrade, movie, id)`.

Fetcher **failed-import** cleanup drives: Radarr vs Sonarr use **separate** schedule interval settings and **separate** dedupe keys / job kinds — independent contracts.

### Refiner (shipped durable families)

Refiner owns ``refiner_jobs`` and in-process Refiner workers. **Each** durable ``refiner.*`` family that exposes operator-controlled timing must keep that timing on **family-local** settings and tasks (no cross-family coupling on the Refiner lane).

Shipped today:

- **`refiner.supplied_payload_evaluation.v1`** — optional periodic enqueue via ``MEDIAMOP_REFINER_SUPPLIED_PAYLOAD_EVALUATION_SCHEDULE_*`` (legacy ``MEDIAMOP_REFINER_LIBRARY_AUDIT_PASS_SCHEDULE_*`` still read when the new keys are absent) and ``refiner_supplied_payload_evaluation_schedule_enabled`` / ``refiner_supplied_payload_evaluation_schedule_interval_seconds`` on ``MediaMopSettings``; failure backoff is local to that enqueue module (process-internal per ADR-0009 “Out of scope”, not shared with Fetcher).
- **`refiner.candidate_gate.v1`** — manual enqueue only in this product pass; **no** shared schedule/cooldown/last-run row with other Refiner families or with Fetcher.

### Trimmer (shipped durable families)

- **`trimmer.trim_plan.constraints_check.v1`** — **manual enqueue only**: no periodic schedule, no shared last-run row with Fetcher or Refiner. Constraint evaluation is process-local to the handler.
- **`trimmer.supplied_trim_plan.json_file_write.v1`** — **manual enqueue only**: same constraint rules, then a single JSON file write under ``MEDIAMOP_HOME``; no periodic schedule and no shared timing state with other modules or families.

### Subber (shipped durable family)

- **`subber.supplied_cue_timeline.constraints_check.v1`** — **manual enqueue only** in this pass: no periodic schedule, no shared last-run row with other modules. Constraint evaluation is process-local to the handler.

### Future Subber durable families

Any additional durable `job_kind` on `subber_jobs` **must** ship with:

- Its own persisted timing and audit fields (or namespaced columns), **or** strictly separate tables if the product demands it — never one shared “last run” or “retry” column for unrelated families.
- Its own env-backed settings in `MediaMopSettings` (or a module-local settings object loaded at startup) for every operator-controlled interval/schedule/cooldown/retry that applies to that family.
- Documentation in the module package and enforcement tests when behavior is non-obvious.

Trimmer and Subber packages point to ADR-0007 for lane ownership; **this ADR** is the timing addendum for scheduled/cooled families (each module’s first shipped constraint-check families here are manual-only).

### Compliance notes (audit snapshot)

| Area | Isolated? | Why |
|------|-----------|-----|
| Fetcher failed-import Radarr vs Sonarr | Yes | Separate `MEDIAMOP_FAILED_IMPORT_*` intervals, separate periodic tasks, separate dedupe keys. |
| Fetcher Arr search four lanes | Yes | Per-lane settings in `MediaMopSettings`, per-lane `(app, action, …)` cooldown log, per-lane prune in `prune_fetcher_arr_action_log`, four last-run columns, four periodic enqueue tasks. |
| Refiner durable families (supplied payload evaluation vs candidate gate) | Yes | Separate job kinds, handlers, and enqueue paths; supplied payload evaluation has its own optional schedule env + interval only for that family; candidate gate has no periodic contract in this pass (manual jobs only). No shared last-run or cooldown between the two. |
| Trimmer durable families (trim plan constraint check + supplied trim plan JSON file write) | Yes (manual-only) | Both families: operator POST enqueue only — no Trimmer periodic task shares timing state with other modules. |
| Subber durable families (cue timeline constraint check) | Yes (manual-only) | Single shipped family; operator POST enqueue only — no Subber periodic task shares timing state with other modules. |

### Soft spot (configuration, not runtime coupling)

If an operator leaves lane-specific env unset, **legacy fallback env** may populate two Sonarr (or two Radarr) lanes with the **same numeric default** from one shared legacy variable. That is **defaults only**; cooldown **state** and last-run **columns** remain per lane. Prefer setting lane-specific env for independent contracts.

## Consequences

- New features undergo review against this ADR when they touch schedules, cooldowns, or retries.
- Tests that lock per-lane behavior (e.g. Fetcher search prune and cooldown keys) are expected to grow with new families.

## Related

- [ADR-0007](ADR-0007-module-owned-worker-lanes.md) — module-owned queues and `job_kind` prefixes.
- [ADR-0008](ADR-0008-mediamop-settings-aggregate-runtime-config.md) — where lane-specific env maps into `MediaMopSettings`.
