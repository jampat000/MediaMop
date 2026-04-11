# ADR-0007: Module-owned worker lanes (SQLite)

## Status

Accepted — **reference template** for Trimmer/Subber; Fetcher + Refiner lanes are live in code.

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
- `modules/fetcher/fetcher_jobs_inspection*.py` / `schemas_*` when product surfaces exist

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

**Refiner today:** generic queue/worker/inspection/recovery stack exists; **production durable kinds** should migrate to **`refiner.*`** as they are introduced. Tests may still use short synthetic kinds until migrated.

**Suggested file map (Refiner)**

- `modules/refiner/jobs_model.py`
- `modules/refiner/jobs_ops.py`
- `modules/refiner/worker_loop.py`
- `modules/refiner/worker_limits.py`
- `modules/refiner/inspection_service.py`
- Refiner inspection/recovery HTTP schemas ship only when Refiner exposes operator APIs for `refiner_jobs`.
- `modules/refiner/router.py` (Refiner-native HTTP only)

**Refiner must not own:** `failed_import.*`, `missing_search.*`, `upgrade_search.*`, `trimmer.*`, `subber.*` (enforced in code).

---

## Trimmer lane (stub — implement when first durable job exists)

| Artifact | Exact name |
|----------|------------|
| SQL table | `trimmer_jobs` |
| ORM model | `TrimmerJob` |
| Status enum | `TrimmerJobStatus` |
| Enqueue | `trimmer_enqueue_or_get_job` |
| Claim | `claim_next_eligible_trimmer_job` |
| Worker starter | `start_trimmer_worker_background_tasks` |
| Worker count env | **`MEDIAMOP_TRIMMER_WORKER_COUNT`** |
| `job_kind` prefix | **`trimmer.`** (e.g. `trimmer.transcode.batch.v1`) |

**Package directory:** `apps/backend/src/mediamop/modules/trimmer/` (mirror Fetcher layout: `trimmer_jobs_model.py`, `trimmer_jobs_ops.py`, `trimmer_worker_loop.py`, …).

**Lifespan:** start Trimmer periodic tasks (if any) and `start_trimmer_worker_background_tasks` **independently** of Refiner/Fetcher counts.

---

## Subber lane (stub — implement when first durable job exists)

| Artifact | Exact name |
|----------|------------|
| SQL table | `subber_jobs` |
| ORM model | `SubberJob` |
| Status enum | `SubberJobStatus` |
| Enqueue | `subber_enqueue_or_get_job` |
| Claim | `claim_next_eligible_subber_job` |
| Worker starter | `start_subber_worker_background_tasks` |
| Worker count env | **`MEDIAMOP_SUBBER_WORKER_COUNT`** |
| `job_kind` prefix | **`subber.`** (e.g. `subber.align_cues.batch.v1`) |

**Package directory:** `apps/backend/src/mediamop/modules/subber/`

**Lifespan:** same independence pattern as Trimmer.

---

## Consequences

- Adding a new **function** in Fetcher is a new **`job_kind`** under `failed_import.` / `missing_search.` / `upgrade_search.` — not a new table unless isolation is proven necessary.
- Adding **Trimmer** or **Subber** is a new **table + worker env + ops names** per this ADR, not new rows in `refiner_jobs`.
- **Cross-lane guards** in `job_kind_boundaries.py` must be extended when a new top-level module gains its own lane (add prefix to forbidden lists on sibling enqueue paths).

## References

- `apps/backend/src/mediamop/modules/queue_worker/job_kind_boundaries.py`
- Fetcher split work (historical): `fetcher_jobs` + `MEDIAMOP_FETCHER_WORKER_COUNT`
