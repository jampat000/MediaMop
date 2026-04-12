# MediaMop — repo-local task tracking

Single canonical backlog for shipped milestones and the next honest slice of work. ADRs remain the authority for locked architecture; this file is for **what is done vs what is next**.

## Completed (Refiner and related suite)

- [x] Refiner ownership vs upstream blocking split verified and correct in domain code.
- [x] Refiner anchor-weighted queue matching verified and correct.
- [x] Refiner per-file remux family shipped (`refiner.file.remux_pass.v1`) with path model and safe defaults.
- [x] Refiner remux pass operator visibility (activity / structured results) shipped for current scope.
- [x] Refiner in-process worker concurrency surfaced to operators (`runtime-settings` + env honesty).
- [x] Refiner path model shipped (persisted watched / work / output; containment and lifecycle rules locked).
- [x] Refiner watched-folder scanning family shipped: `refiner.watched_folder.remux_scan_dispatch.v1` (manual trigger, media scan, gate-equivalent ownership/blocking, optional remux enqueue, duplicate guard, activity summary, Refiner page UI + POST enqueue API).
- [x] Refiner jobs inspection / operator control surface: `GET …/refiner/jobs/inspection`, Refiner page queue table, `POST …/refiner/jobs/{id}/cancel-pending` (pending-only; operators); finished outcomes remain on Activity.
- [x] Refiner watched-folder periodic scanning: optional Refiner-only asyncio enqueue loop for `refiner.watched_folder.remux_scan_dispatch.v1` (separate env enable/interval + periodic remux flags from supplied payload evaluation); scan-level idle guard; `scan_trigger` in activity summary; runtime settings snapshot + UI honesty (restart required).

## Roadmap item 6 — Refiner jobs inspection / operator control surface

**Completion criteria (must all be true to tick):**

1. Operators can list recent `refiner_jobs` rows with **lifecycle fields from the job table** (status, lease, attempts, errors, timestamps, kind, dedupe key, payload) without scrolling the global Activity feed as the only queue view.
2. **Result / outcome truth** for finished work remains on **Activity** (and existing per-family surfaces); the jobs list does not pretend to replace remux structured results or scan summaries.
3. Any **control** is narrow, explicit, and safe: only **cancel pending** (never leased/running, never completed/failed terminal rows). If cancel is shipped, re-enqueue with the same dedupe key after cancel must remain possible (no permanent dedupe deadlock).

### 6 — status

- [x] **Done** — `GET /api/v1/refiner/jobs/inspection` (optional `status=` repeat; default = newest across all statuses), Refiner page “Refiner jobs (queue)” section, `POST /api/v1/refiner/jobs/{id}/cancel-pending` (operators; pending-only; tombstone `dedupe_key` for reuse), `cancelled` status on `refiner_jobs`, tests.

## Roadmap item 7 — Refiner watched-folder periodic scanning family

**Completion criteria (must all be true to tick):**

1. The existing manual `refiner.watched_folder.remux_scan_dispatch.v1` enqueue path remains intact.
2. A **Refiner-local** optional periodic enqueue exists (same `lifespan.py` asyncio pattern as supplied payload evaluation), with **its own** enable + interval + optional periodic remux flags on `MediaMopSettings` — **no** shared timing contract with Fetcher or other Refiner families.
3. **Scan-level duplicate guard:** periodic tick does not enqueue a new scan row while another scan of this job kind is `pending` or `leased`.
4. **File-level duplicate guard:** unchanged inside the scan handler (same-run set + active remux queue check).
5. Operators can see periodic config in the Refiner runtime snapshot and honest copy states **restart** is required for env changes.
6. Activity / JSON summary distinguishes **manual vs periodic** via an explicit field (`scan_trigger`).

### 7 — status

- [x] **Done** — `refiner_watched_folder_remux_scan_dispatch_enqueue.py`, `refiner_watched_folder_remux_scan_dispatch_periodic_enqueue.py`, `lifespan.py` wiring, `MediaMopSettings` + `.env.example`, runtime API + web Refiner sections, ADR-0007/0009 alignment, tests.

## Roadmap item 8 — Central Settings UI (suite: Global + Security only)

**Scope (explicit):** The **central** `/app/settings` page owns **MediaMop suite** presentation and **read-only security posture** — not Fetcher, not Sonarr/Radarr, not Refiner/Trimmer/Subber module config.

**Completion criteria (must all be true to tick):**

1. **Global:** Operators and admins can edit **product display name** and **optional signed-in home dashboard notice** in the UI; values persist in the **`suite_settings`** SQLite singleton (Alembic migration), via `GET`/`PUT /api/v1/suite/settings` (CSRF + operator auth on write). Viewers can read but not save.
2. **Security:** All signed-in roles see a **read-only** overview from **startup-loaded** `MediaMopSettings` (`GET /api/v1/suite/security-overview`) with plain-language fields and an explicit note that **configuration file + restart** are required to change those values — no fake “saved” behavior for env-only settings.
3. **Honesty:** Global saves apply immediately for the running app (database-backed). Security values are **not** presented as live-editable in the browser. No duplicate editing surface for Refiner paths, Fetcher failed-import settings, or other module-owned truth.
4. **Central page purity:** The central Settings route **does not** surface Sonarr, Radarr, Fetcher cleanup toggles, or Fetcher schedules (asserted in tests / copy).
5. **Product wiring:** Saved **product display name** appears in the signed-in shell (sidebar); optional **home notice** appears on the dashboard when set.
6. **Tests:** Backend API + migration head + security overview builder; frontend settings page (no Sonarr/Radarr strings, viewer cannot save).

### 8 — status

- [x] **Done** — `suite_settings` table + model/service/schemas, `GET`/`PUT /api/v1/suite/settings`, `GET /api/v1/suite/security-overview`, web Settings page (Global / Security tabs), shell + dashboard wiring, `docs/TASKS.md` split for Fetcher milestone below, tests.

## Roadmap item 9 — Fetcher integration settings UI (future)

**Not part of item 8.** Dedicated Fetcher module work when prioritized:

- Sonarr/Radarr (and shared ARR) connection and search/cleanup schedule surfaces that belong **on Fetcher** (or clearly Fetcher-owned routes), not the central suite Settings page.
- Honest separation from suite Global/Security and from Refiner-owned path/runtime settings.

### 9 — status

- [ ] **Not started** — backlog only.

## Active / next (after item 8)

- [ ] Roadmap item 9 (Fetcher integration settings UI) when prioritized.
- [ ] Richer Activity rendering for watched-folder scan summaries if plain `detail` text is not enough.
- [ ] Other product milestones as prioritized (no duplicate task file).
