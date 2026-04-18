# ADR-0007: Module-owned worker lanes (SQLite)

## Status

Accepted — **four module lanes** are live: ``fetcher_jobs``, ``refiner_jobs``, ``pruner_jobs``, ``subber_jobs`` (see tables below).

## Context

MediaMop is **SQLite-first**: one writer per database. Durable background work must be **sharded by module-owned tables** and **in-process worker pools**, not multiplexed through a single hidden global queue. Job kinds name **function** inside a module; table + env + ops name **module ownership**.

## Decision

### Global rules

1. **One persisted jobs table per module lane** (default). Multiple `job_kind` values per table are expected.
2. **`job_kind` is `"{namespace}.{function}.{variant}"`** where `namespace` is the **lane prefix** tied to the owning module (see below).
3. **No shared “jobs” table** partitioned only by `job_kind` as the long-term shape.
4. **Enqueue / claim / worker startup** for a module stay in that module’s package (composition root may wire lifespan only).
5. **Cross-lane prefixes are rejected** at enqueue and at worker claim boundaries (see `mediamop.modules.queue_worker.job_kind_boundaries`).

### Fetcher lane (implemented)

| Artifact | Name |
|----------|------|
| SQL table | `fetcher_jobs` |
| ORM model | `FetcherJob` |
| Status enum | `FetcherJobStatus` |
| Enqueue | `fetcher_enqueue_or_get_job` |
| Claim | `claim_next_eligible_fetcher_job` |
| Worker entry | `start_fetcher_worker_background_tasks` |
| Worker count env | `MEDIAMOP_FETCHER_WORKER_COUNT` |
| Reserved `job_kind` prefixes | `failed_import.`, `missing_search.`, `upgrade_search.` |

**Suggested file map (Fetcher; extend as needed)**

- `modules/fetcher/fetcher_jobs_model.py`
- `modules/fetcher/fetcher_jobs_ops.py`
- `modules/fetcher/fetcher_worker_loop.py`
- `modules/fetcher/fetcher_worker_limits.py` (if clamping)
- `modules/fetcher/failed_import_worker_ports.py` (typed ports for failed-import worker wiring)
- `modules/fetcher/fetcher_jobs_inspection*.py` / `schemas_*` / `fetcher_jobs_api.py` (read-only ``GET /fetcher/jobs/inspection``)

### Refiner lane (implemented substrate)

| Artifact | Name |
|----------|------|
| SQL table | `refiner_jobs` |
| ORM model | `RefinerJob` |
| Status enum | `RefinerJobStatus` |
| Enqueue | `refiner_enqueue_or_get_job` |
| Claim | `claim_next_eligible_refiner_job` |
| Worker entry | `start_refiner_worker_background_tasks` |
| Worker count env | `MEDIAMOP_REFINER_WORKER_COUNT` |
| Reserved `job_kind` prefix (new durable Refiner work) | **`refiner.`** |

**Refiner today:** shipped production durable kinds use **`refiner.*`** only on ``refiner_jobs`` (including ``refiner.file.remux_pass.v1`` for per-file ffprobe + remux planning / optional ffmpeg, and ``refiner.watched_folder.remux_scan_dispatch.v1`` for a watched-folder scan that classifies media candidates and may enqueue per-file remux jobs — manual POST plus optional Refiner-only periodic enqueue driven by ``MEDIAMOP_REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_SCHEDULE_*`` env at process start). Tests may still use short synthetic kinds where the worker loop’s unprefixed-row guard is under test. Per-file remux enqueue: ``POST /api/v1/refiner/jobs/file-remux-pass/enqueue``; watched-folder scan enqueue: ``POST /api/v1/refiner/jobs/watched-folder-remux-scan-dispatch/enqueue``; persisted-queue inspection (read lifecycle from ``refiner_jobs``): ``GET /api/v1/refiner/jobs/inspection``; optional pending-only abandon: ``POST /api/v1/refiner/jobs/{id}/cancel-pending`` (operators; CSRF); watched/work/output roots: persisted Refiner path settings (``GET/PUT /api/v1/refiner/path-settings`` on singleton ``refiner_path_settings``). Read-only worker snapshot for operators: ``GET /api/v1/refiner/runtime-settings`` (maps ``MEDIAMOP_REFINER_WORKER_COUNT`` after clamp; Refiner-only; not a cross-lane control).

**Suggested file map (Refiner)**

- `modules/refiner/jobs_model.py`
- `modules/refiner/jobs_ops.py`
- `modules/refiner/worker_loop.py`
- `modules/refiner/worker_limits.py`
- `modules/refiner/inspection_service.py`
- Refiner inspection/recovery HTTP schemas ship only when Refiner exposes operator APIs for `refiner_jobs`.
- `modules/refiner/router.py` (Refiner-native HTTP only)

**Refiner must not own:** `failed_import.*`, `missing_search.*`, `upgrade_search.*`, `pruner.*`, `subber.*`, or legacy `trimmer.*` (enforced in code).

---

## Pruner lane (Phase 1 — infrastructure only)

| Artifact | Exact name |
|----------|------------|
| SQL table | `pruner_jobs` |
| ORM model | `PrunerJob` |
| Status enum | `PrunerJobStatus` |
| Enqueue | `pruner_enqueue_or_get_job` |
| Claim | `claim_next_eligible_pruner_job` |
| Worker starter | `start_pruner_worker_background_tasks` |
| Worker count env | **`MEDIAMOP_PRUNER_WORKER_COUNT`** |
| `job_kind` prefix | **`pruner.`** |

**Phase 1:** durable queue + workers + cross-lane guards only. **No** shipped Pruner `job_kind` families or product HTTP enqueue routes yet (removal-focused work lands in later phases). The historical ``trimmer_jobs`` table from revision ``0009_trimmer_jobs`` is dropped at head by ``0025_pruner_jobs_drop_trimmer_jobs``; the string prefix ``trimmer.`` is reserved as **legacy/forbidden** on all lanes (see `job_kind_boundaries.py`).

**Package directory:** `apps/backend/src/mediamop/modules/pruner/` (`pruner_jobs_model.py`, `pruner_jobs_ops.py`, `worker_loop.py`, `pruner_job_handlers.py`, …).

**Lifespan:** `start_pruner_worker_background_tasks` runs **independently** of Refiner/Fetcher worker counts (no shared timing tables).

**Forward design:** ``docs/pruner-forward-design-constraints.md`` — TV vs Movies independence, per media-server-instance ownership (Emby, Jellyfin, Plex as peers), no single global server config.

---

## Subber lane (implemented)

| Artifact | Exact name |
|----------|------------|
| SQL table | `subber_jobs` |
| ORM model | `SubberJob` |
| Status enum | `SubberJobStatus` |
| Enqueue | `subber_enqueue_or_get_job` |
| Claim | `claim_next_eligible_subber_job` |
| Worker starter | `start_subber_worker_background_tasks` |
| Worker count env | **`MEDIAMOP_SUBBER_WORKER_COUNT`** |
| `job_kind` prefix | **`subber.`** |

**Shipped durable families (Subber v1):** `subber.subtitle_search.{tv,movies}.v1`, `subber.library_scan.{tv,movies}.v1`, `subber.webhook_import.{tv,movies}.v1` — OpenSubtitles-backed SRT download and *arr webhook import; TV and Movies are independent job streams and DB state. HTTP surface: `/api/v1/subber/*` (see module router).

**Package directory:** `apps/backend/src/mediamop/modules/subber/`

**Lifespan:** `start_subber_worker_background_tasks` runs **independently** of other module worker counts.

---

## Related

- [ADR-0009](ADR-0009-suite-wide-timing-isolation.md) — **Timing isolation:** intervals, schedule windows, cooldowns, retries, last-run timestamps, and timing-derived pruning are **per module** and **per job family**; no shared operator timing contracts across lanes.

---

## Consequences

- Adding a new **function** in Fetcher is a new **`job_kind`** under `failed_import.` / `missing_search.` / `upgrade_search.` — not a new table unless isolation is proven necessary.
- Adding **Pruner** or **Subber** is a new **table + worker env + ops names** per this ADR, not new rows in `refiner_jobs`.
- **Cross-lane guards** in `job_kind_boundaries.py` must be extended when a new top-level module gains its own lane (add prefix to forbidden lists on sibling enqueue paths).

## References

- `apps/backend/src/mediamop/modules/queue_worker/job_kind_boundaries.py`
- Fetcher split work (historical): `fetcher_jobs` + `MEDIAMOP_FETCHER_WORKER_COUNT`
