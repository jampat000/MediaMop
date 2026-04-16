# MediaMop — repo-local task tracking

Single canonical backlog for shipped milestones and the next honest slice of work. ADRs remain the authority for locked architecture; this file is for **what is done vs what is next**.

## Completed (Refiner and related suite)

- [x] Refiner ownership vs upstream blocking split verified and correct in domain code.
- [x] Refiner anchor-weighted queue matching verified and correct.
- [x] Refiner per-file remux family shipped (`refiner.file.remux_pass.v1`) with path model and safe defaults.
- [x] Refiner remux pass operator visibility (activity / structured results) shipped for current scope.
- [x] Refiner in-process worker concurrency surfaced to operators (`runtime-settings` + env honesty).
- [x] Refiner path model shipped (persisted watched / work / output; containment and lifecycle rules locked).
- [x] Refiner work/temp stale sweep (Pass 2 + 13b): per-scope periodic ``refiner.work_temp_stale_sweep.v1`` (Movies vs TV independent gates, dedupe, schedule, reporting; shared-root fail-safe; shared min-stale-age only as documented exception).
- [x] Refiner Pass 3a (Movies output-folder cleanup): after successful Movies remux, optional full per-title output folder delete when Radarr library has no ``movieFile`` path inside that folder, age + active Movies remux gates pass; cascade bounded to output root; ``refiner_movie_output_cleanup.py``.
- [x] Refiner Pass 3b (TV output-folder cleanup): after successful TV remux, optional full season output folder delete when Sonarr episode-file library paths, age (direct-child episode media only), and active TV remux gates pass; show-folder cascade bounded to TV output root; ``refiner_tv_output_cleanup.py``.
- [x] Refiner Pass 4 (failure cleanup sweep): periodic per-scope cleanup for terminal failed Refiner remux jobs after grace period (Movies/TV independent), ARR queue boundary checks, dry-run skip, bounded source/output/temp cleanup, lock-safe behavior, plain activity truth.
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

**Scope (explicit):** The **central** `/app/settings` page owns **MediaMop suite** presentation and **read-only security posture** — not Fetcher, not Sonarr/Radarr, not Refiner/Pruner/Subber module config.

**Completion criteria (must all be true to tick):**

1. **Global:** Operators and admins can edit **product display name** and **optional signed-in home dashboard notice** in the UI; values persist in the **`suite_settings`** SQLite singleton (Alembic migration), via `GET`/`PUT /api/v1/suite/settings` (CSRF + operator auth on write). Viewers can read but not save.
2. **Security:** All signed-in roles see a **read-only** overview from **startup-loaded** `MediaMopSettings` (`GET /api/v1/suite/security-overview`) with plain-language fields and an explicit note that **configuration file + restart** are required to change those values — no fake “saved” behavior for env-only settings.
3. **Honesty:** Global saves apply immediately for the running app (database-backed). Security values are **not** presented as live-editable in the browser. No duplicate editing surface for Refiner paths, Fetcher failed-import settings, or other module-owned truth.
4. **Central page purity:** The central Settings route **does not** surface Sonarr, Radarr, Fetcher cleanup toggles, or Fetcher schedules (asserted in tests / copy).
5. **Product wiring:** Saved **product display name** appears in the signed-in shell (sidebar); optional **home notice** appears on the dashboard when set.
6. **Tests:** Backend API + migration head + security overview builder; frontend settings page (no Sonarr/Radarr strings, viewer cannot save).

### 8 — status

- [x] **Done** — `suite_settings` table + model/service/schemas, `GET`/`PUT /api/v1/suite/settings`, `GET /api/v1/suite/security-overview`, web Settings page (Global / Security tabs), shell + dashboard wiring, plus suite-level Global fields for activity logging toggle, app timezone, and activity retention days; Security now includes in-app `POST /api/v1/auth/change-password` (current password required, session revoke on success) alongside read-only startup posture, tests.

## Roadmap item 9 — Fetcher module: Sonarr and Radarr settings (connections, searches, schedules)

**Scope (explicit):** Fetcher-owned **TV library (Sonarr)** and **movie library (Radarr)** operator surfaces: **database-backed** connection fields on `fetcher_arr_operator_settings` (encrypted API keys; env fallback when the row is incomplete), **database-backed** automatic search lane preferences on the same singleton, and one-time **connection checks** with outcomes on **Activity** (`fetcher.arr_connection_test_succeeded` / `fetcher.arr_connection_test_failed`). Lives on the **Fetcher page** and `GET`/`PUT`/`POST` under `/api/v1/fetcher/…` — **not** the central `/app/settings` page.

**Parity targets (from Fetcher reference app):** per-lane enable, how often automatic checks are queued, schedule windows (days + start/end), batch limits, retry spacing, and explicit “check connection” actions. **Not** migrated: monolithic AppSettings backup/restore, Windows updater, or Fetcher auth/IP allowlist as MediaMop auth.

**Persistence truth:**

- **SQLite singleton (`fetcher_arr_operator_settings`) — connections:** per-app **enable**, **base URL**, and **API key** (Fernet ciphertext from `MEDIAMOP_SESSION_SECRET`; not plain text at rest), plus **last connection test** fields. Operators edit these on the Fetcher **Connections** tab; saves are real. If a link is enabled but URL/key are missing or unusable in the row, runtime **falls back** to env (`MEDIAMOP_ARR_SONARR_*` / `MEDIAMOP_ARR_RADARR_*` and legacy `MEDIAMOP_FETCHER_*` where supported) so upgrades stay honest — the UI `connection_note` explains that split in plain language.
- **Env / server file:** still the compatibility **fallback** for URL/API key when the DB row does not carry a usable secret pair; operators can keep using the file during migration. Central Settings does not own these values.
- **SQLite singleton (`fetcher_arr_operator_settings`) — search lanes:** all four lanes’ operational fields (enabled, `max_items_per_run`, `retry_delay_minutes`, schedule gate + days + start/end, `schedule_interval_seconds`). This is what **running** search handlers and periodic enqueue read after migration.
- **Still env-only today:** schedule **time zone name** (`fetcher_arr_search_schedule_timezone` on `MediaMopSettings`) — shown read-only on the operator settings payload; moving it into the DB table is explicitly **deferred**.
- **Honesty note:** older env keys for per-lane search toggles and intervals still exist on `MediaMopSettings` for compatibility and tests, but **lane runtime behavior follows the SQLite row** once the app is migrated. Do not treat those env fields as live toggles for production behavior after this milestone.

**Restart / apply behavior:**

- Saving lane fields (windows, limits, retry, enable) applies on the next worker pass or enqueue tick without an API restart, except **how often the background loop queues a new check** (`schedule_interval_seconds`): the periodic asyncio tasks read that value on each sleep cycle, but the UI still tells operators to **restart the API** after changing intervals so expectations match every deployment style.
- Connection checks do not change saved settings.

**Relationship to existing Fetcher surfaces:** failed-import **cleanup policy**, **runtime visibility**, **automation summary** (Overview UI label: **Current search setup**), **jobs inspection**, and **manual enqueue** stay on the **Fetcher route** (no new standalone Fetcher settings page). This item does not duplicate their APIs; **IA correction** (below) places *arr* automation and connections into tabs and removes the long stacked settings dump.

**Explicit non-goals:** central suite Settings changes; Refiner/Pruner/Subber settings; backup/restore; updater; a generic settings framework; persistent “health dashboards” derived from a single test click; a **separate** Fetcher settings route.

**Scope lock — UI correction pass (historical):** An earlier slice locked Fetcher-only web paths. **Current tree:** Connections credentials ship with **backend** migration `0014_fetcher_arr_connection_fields`, resolver + encrypted fields, and web panels under `pages/fetcher/**` / `lib/fetcher/**`. Further item 9 polish still respects “no central Settings / no unrelated modules” unless a later milestone explicitly widens scope.

**What stays locked (product + architecture):**

- Sonarr/Radarr operator surfaces stay on the **Fetcher** page and `/api/v1/fetcher/…`, not central `/app/settings` (Global + Security only there).
- Connection test outcomes go to **Activity**; **Connections** owns editable URL/key (DB-backed, encrypted) with honest env fallback when the row is incomplete; lane **operational** preferences stay **DB-backed** (`fetcher_arr_operator_settings`).
- User-facing copy stays **plain and non-technical** (no jargon wall).

**Fetcher page IA (target; web is iterative):** One Fetcher route with **tabs or submenu** (not a separate settings page). Tabs include **Failed imports** for the download-queue workspace. **Treat the Fetcher web slice as ongoing** until copy, inner layouts, and operator review say otherwise — do not “close” this track just because the first tabbed layout shipped.

| Area | Content |
|------|--------|
| **Overview** | **At a glance** (Connections → Sonarr → Radarr → Failed imports), **Needs attention**, **Current search setup** (read-only lane snapshot), **Failed imports that need attention** (headline + link — no duplicate Connections block; optional link probes surface in Needs attention only). |
| **Connections** | **Side-by-side** **Sonarr** then **Radarr** panels: enable switch, URL, masked API key with show/hide, **Save Sonarr** / **Save Radarr** / **Test Sonarr** / **Test Radarr**, last **Connection status** in-panel; tests also log to **Activity**. Schedule time zone and interval/restart notes for **search** timing stay on **Sonarr (TV)** / **Radarr (Movies)** tabs. |
| **Sonarr (TV)** | **TV-specific** automatic search lane settings (missing + upgrade); SQLite-backed operator fields; time zone + interval / restart plain-language notes for schedules. |
| **Radarr (Movies)** | **Movie-specific** automatic search lane settings (missing + upgrade); same persistence rules; same schedule notes as TV tab. |
| **Failed imports** | **Failed-import** workspace (cleanup, runtime, jobs inspection, manual enqueue / run-now) — same route, dedicated tab. |

**Backend/persistence and APIs:** lane prefs and connection rows on `fetcher_arr_operator_settings` are implemented; connection **PUT** routes and resolver wiring ship with migration **0014**; further item 9 work is mostly **web polish and honesty** unless a new API gap appears.

**Completion criteria (must all be true to tick):**

1. Operators can read and (if admin/operator) save the four automatic search lanes on the Fetcher page; viewers see read-only data.
2. Connection fields and time zone notes match persistence rules above; no fake “saved” messaging where nothing is written (env fallback remains documented in `connection_note` when relevant).
3. `POST …/fetcher/arr-operator-settings/connection-test` runs a real v3 status call when credentials exist, and always writes a plain-language row to **Activity** (success or failure, including “not configured”).
4. Central Settings page remains free of Sonarr/Radarr strings (existing test kept green).
5. Tests cover API auth/roles, validation, connection-test → Activity, schema head includes `fetcher_arr_operator_settings`, and Fetcher page tests cover the **tabbed/submenu** structure.
6. **IA:** Fetcher page matches the **Overview / Connections / Sonarr (TV) / Radarr (Movies) / Failed imports** table above: **Overview** — landing tab in order **At a glance** → **Needs attention** → **Current search setup** → **Failed imports that need attention** (no repeated lower Connections/service section; no “Download queue preview” naming); deeper detail stays on the other tabs; **Connections** — Sonarr then Radarr panels **side by side** (stacked on small screens) with save/test and in-panel status; **Sonarr (TV)** / **Radarr (Movies)** — lane editors + schedule time zone / restart plain notes; **Failed imports** — full failed-import workspace. **No** long single-column dump mixing those roles.
7. **Scope:** Item 9 UI correction satisfies the **Scope lock** above (Fetcher-only paths; no unrelated app or backend churn).

### 9 — status

- [x] **Backend shipped** — migration `0013_fetcher_arr_operator_settings`, prefs + worker/enqueue wiring, `GET`/`PUT /api/v1/fetcher/arr-operator-settings`, `POST …/connection-test`, Activity constants, backend tests; migration **`0014_fetcher_arr_connection_fields`**, encrypted connection keys, `PUT …/arr-connection/{sonarr,radarr}`, resolver (DB → env fallback) across Fetcher/Refiner call sites, backend tests for connection APIs.
- [ ] **Fetcher web / operator surface — open (same item 9)** — Tabbed shell remains (**Overview / Connections / Sonarr (TV) / Radarr (Movies) / Failed imports**). **Truth pass (web):** Overview **Needs attention** routes connected-but-idle search setups to the correct **Sonarr (TV)** / **Radarr (Movies)** tabs (not only Connections); **Current search setup** shows missing vs upgrade cadence separately when saved lanes differ (no silent pick of one lane). **Independence pass (API + web):** automatic search lanes save via **`PUT …/arr-operator-settings/lanes/{sonarr_missing|sonarr_upgrade|radarr_missing|radarr_upgrade}`** (one lane per request; bulk `PUT …/arr-operator-settings` retained for compatibility); failed-import cleanup saves via **`PUT …/cleanup-policy/tv-shows`** and **`PUT …/cleanup-policy/movies`** with per-card React Query pending; bulk cleanup `PUT` retained for compatibility. **Perfection-gate race fix:** lane refetch after a successful save no longer wipes unsaved draft edits in other lanes; tests cover preserving unsaved lane edits across query refresh. **Shipped in this TV/Movies structure pass:** **Sonarr (TV)** and **Radarr (Movies)** each use **two** bordered bubbles (**missing** + **upgrades**) with locked titles and intro lines; inside each bubble, controls follow **Enable / Disable** (same On/Off switch style as Connections) → **Run interval** → **Schedule** (locked helper + **Limit to these hours** switch + day/time fields) → **Search limit** → **Retry cooldown** → **Save** with locked button labels (**Save missing TV show searches** / **Save TV upgrades** / **Save missing movie searches** / **Save movie upgrades**); per-bubble dirty gating; shared **`FetcherEnableSwitch`** with Connections for visual parity. **Connections truth + UX pass (unchanged):** **`status_headline`**, **`connection_note`**, effective-vs-saved hints, per-panel test pending, backend PUT/headline tests. **This pass added:** clearer save confirmation (accent banner + brief panel highlight, no duplicate “Saved.” in connection status); stronger Fetcher action buttons; aligned Radarr “Missing movies” casing; spacing rhythm tweaks. **Overview correction pass (web):** locked four-section order; **At a glance** inner cards **Connections → Sonarr → Radarr → Failed imports**; **Automation summary** renamed **Current search setup**; **Download queue preview** replaced by **Failed imports that need attention** with locked subtext; paired labels use **Sonarr (TV)** / **Radarr (Movies)**; removed duplicate **Connections & optional service link** block from Overview. **Still in scope:** Failed imports density, cross-tab drafts, accessibility, deep links, backup/restore — item 9 **not** closed.

## Roadmap item 10 — Pruner removal product (library / server integrations)

**Status:** **Open** — Pruner **Phase 1** ships the durable lane only (`pruner_jobs`, `pruner.*` prefix, workers); see `docs/adr/ADR-0007-module-owned-worker-lanes.md` and `docs/pruner-forward-design-constraints.md`. **Phase 2+** covers rule-based removal against **Emby, Jellyfin, and Plex** as peers, with **per server instance** ownership and **independent TV vs Movies** surfaces — not a replay of the old trim-plan experiment or Refiner remux work.

### 10 — status

- [ ] **Open** — no shipped Pruner removal job families yet; criteria TBD per forward-design doc.

## Roadmap item 11 — Refiner Movies watched-folder release cleanup (Pass 1)

**Scope (explicit):** **Movies (`media_scope=movie`) only.** After a successful live `refiner.file.remux_pass.v1`, optionally remove the **entire release folder** (immediate parent of the media file) under the saved Movies watched folder, with output completeness checks, file-lock tolerance, and cascade removal of empty parents **up to but not including** the watched root. **TV** keeps the existing single-file delete only; no shared cleanup code path.

**Completion criteria (must all be true to tick):**

1. **Scope guard:** If `media_scope` is not `movie`, Movies folder cleanup does not run; TV behavior remains single-file deletion only; logs / activity state this plainly.
2. **Never delete the watched root** and **never delete outside the watched root** (verified with `Path.relative_to`); if the media file’s immediate parent **is** the watched root, cleanup is skipped and logged.
3. **Output gate:** Before any watched-side deletion for Movies, the expected output file must exist, be non-zero size, and be at least 1% of the source file size; otherwise skip deletion and log (minimum safety gate, not a full integrity check).
4. **Dry run:** Zero filesystem mutations for cleanup; activity / logs describe what would happen for Movies when applicable.
5. **Locks:** Permission or OS errors during folder removal are non-fatal: log which path failed, skip that folder removal, job still succeeds.
6. **Cascade:** After removing the release folder, remove empty parents until a non-empty folder or the watched root is reached; never remove the watched root.
7. **Activity JSON** includes the agreed operator-facing fields (`source_folder_deleted`, `source_folder_path`, `source_folder_skip_reason`, `output_completeness_check`, sizes, `cascade_folders_deleted`, etc.).
8. **Tests** cover Movies success (folder + cascade), skips (root parent, missing/small output, locks), dry-run preview, TV unchanged path, and scope guard.

### 11 — status

- [x] **Pass 1 done (Movies watched-folder release folder + gates)** — `refiner_file_remux_pass_run.py` (+ path runtime preview for dry-run copy), `refiner_file_remux_pass_handlers.py`, `refiner_path_settings_service.py`, `refiner_remux_rules.py` docstring; tests in `test_refiner_file_remux_pass_run.py`.

## Roadmap item 12 — Refiner TV watched-folder season cleanup (Pass 1b)

**Scope (explicit):** **TV (`media_scope=tv`) only.** After a successful live `refiner.file.remux_pass.v1`, optionally remove the **entire season folder** (immediate parent of the episode file) when **every** direct-child episode media file passes the four-check gate (Sonarr queue, active TV remux jobs, Refiner-processed output verification, or never-processed minimum age). Optional **show-folder cascade** removes empty parents up to but not including the TV watched root. **Movies** Pass 1 behavior stays separate — no shared cleanup implementation.

**Completion criteria (must all be true to tick):**

1. **Scope guard:** Non-`tv` scopes never run TV season cleanup; Movies code paths are unchanged.
2. **Episode set:** Only **direct children** of the season folder matching `is_refiner_media_candidate` — no recursive subfolder episode discovery.
3. **Four-check gate:** All episodes must pass Sonarr queue check, active TV remux job check (path + `media_scope=tv`, excluding the current job), processed-output verification (Activity-backed successful live TV outcomes + output size gate), or never-processed + minimum age — any failure blocks the whole season.
4. **Sonarr unreachable:** If Sonarr queue data cannot be loaded, skip the entire season cleanup and log — no deletions.
5. **Never delete the TV watched root** and never delete outside it (`Path.relative_to`); if the season folder **is** the watched root, skip and log.
6. **Dry run:** Zero filesystem mutations; plain-language summary of what would happen.
7. **File locks:** `PermissionError` / `OSError` on season delete skip the season, log, job still succeeds.
8. **Activity JSON** includes `tv_season_folder_deleted`, `tv_season_folder_path`, `tv_season_folder_skip_reason`, `tv_episode_check_summary`, `tv_output_completeness_check`, `tv_cascade_folders_deleted`, `tv_sonarr_unreachable`.
9. **Tests** cover deletes, blocks (queue, active job, output, age, Sonarr down, dry run, cascade, scope guard, cross-scope jobs, direct-child episode set).

### 12 — status

- [x] **Pass 1b done (TV season folder + cascade)** — `refiner_tv_season_folder_cleanup.py`, `refiner_file_remux_pass_run.py` / handlers wiring, Libraries disclosure copy, `test_refiner_tv_season_folder_cleanup.py` + TV remux integration in `test_refiner_file_remux_pass_run.py`.

## Roadmap item 13 — Refiner work/temp stale cleanup (Pass 2)

**Scope (explicit):** **Refiner work/temp folders only.** Periodic (or manually enqueued) sweep removes **stale, Refiner-owned** temp files (e.g. ``*.refiner.*`` from ``remux_to_temp_file``, dry-run placeholder) under resolved Movies and TV **effective** work roots. **No** watched-folder source/output deletion; **no** Arr APIs; **no** change to Pass 1 / Pass 1b watched-folder cleanup.

### 13b — Pass 2 separation correction (Movies / TV independence)

**Problem:** Initial Pass 2 used a **global** remux gate, **one** deduped sweep job, **merged** reporting, **shared** schedule knobs, and **deduped** identical work roots — cross-scope blocking and merged operator truth.

**Completion criteria (must all be true to tick separation correction):**

1. **Per-scope roots:** Movies sweep reads only the Movies effective work root; TV sweep only the TV effective work root — never the other scope’s path.
2. **Same physical root:** If resolved Movies work == resolved TV work, **no automatic deletes** in either scope’s job (fail-safe); plain ``temp_cleanup_skipped_reason`` + ``temp_cleanup_shared_work_root_conflict: true``; no silent merge pretending independence.
3. **Per-scope active gate:** A pending/leased ``refiner.file.remux_pass.v1`` job blocks **only** the sweep whose payload ``media_scope`` matches (legacy payloads without ``media_scope`` treated as Movies).
4. **Per-scope scheduling:** Separate periodic enqueue / dedupe rows for Movies vs TV (same job kind allowed with scope in payload + distinct dedupe keys).
5. **Per-scope reporting:** Each sweep run’s structured result includes ``media_scope`` and scope-local ``temp_cleanup_*`` fields (one scope per job completion / Activity row).
6. **Stale age:** Either split per scope **or** one shared ``min_stale_age`` documented as a **narrow exception** (same temp artifact semantics).
7. **Dry run / locks / candidates:** Unchanged product rules (zero FS mutation on dry run; lock-safe skip; Refiner-owned filename rules only).
8. **Tests** prove cross-scope non-blocking, per-scope dedupe, shared-root policy, and reporting.

**Completion criteria (original Pass 2 — still required):**

1. **Candidates:** Only artifacts Refiner creates by name/pattern in code (no broad “old file” sweeps).
2. **Roots:** Sweep bounded to the effective work root for **that** job’s ``media_scope`` only; never paths outside that root.
3. **Active-job gate:** Per-scope only (see 13b).
4. **Stale age:** As in 13b.
5. **Dry run:** Payload ``dry_run: true`` — zero filesystem deletes; result lists what would be removed.
6. **Locks:** ``OSError``/``PermissionError`` on delete — skip file, log, continue; job does not crash.
7. **Activity / structured result:** Per-scope ``temp_cleanup_*`` plus ``media_scope`` (and shared-root conflict flag when applicable).
8. **Tests** cover delete/stale/fresh, non-candidate untouched, per-scope active gate, both scopes independently, custom roots, lock skip, dry run, bounded roots, shared-root block.
9. **Refiner-only** module layout (``refiner_temp_cleanup.py`` + job kind + periodic enqueue + lifespan wiring).

### 13 — status

- [x] **Pass 2 + 13b separation correction shipped** — Per-scope ``refiner.work_temp_stale_sweep.v1`` (payload ``media_scope`` + dedupe keys ``…:movie`` / ``…:tv``), per-scope remux gate (payload ``media_scope``; legacy remux payloads count as Movies), shared-root fail-safe (no deletes, plain skip reason + ``temp_cleanup_shared_work_root_conflict``), per-scope schedule env + runtime/UI, shared ``MIN_STALE_AGE`` documented narrow exception, ``test_refiner_temp_cleanup.py``.

## Roadmap item 14 — Refiner Pass 3a (Movies output-folder cleanup)

**Scope (explicit):** **Movies only** (``media_scope=movie``). Deletes the **immediate parent folder of the written movie file** under the resolved **Movies output root** (full tree delete + cascade of empty parents up to, but not including, the output root). **No** watched-folder changes, **no** work/temp sweep, **no** TV output cleanup, **no** Pass 1/1b/2 behavior changes.

**Completion criteria (must all be true to tick):**

1. **Non-movie abort:** If ``media_scope`` is not ``movie``, output-folder cleanup does not run; plain skip reason if invoked incorrectly.
2. **Root bounds:** Target folder must be strictly under resolved Movies output root; never delete the output root; never delete outside output root (``Path.relative_to``).
3. **Radarr library truth (mandatory):** Before delete, load Radarr library (``GET /api/v3/movie``) and block if **any** ``movieFile.path`` resolves **inside** the candidate output folder. Queue membership is **not** the gate. If Radarr is unreachable or the library list cannot be read, **skip** deletion (fail safe).
4. **Minimum age:** Candidate folder is eligible only if the **newest** mtime among files under that folder is older than ``refiner_movie_output_cleanup_min_age_seconds`` (default 48h, env at process start).
5. **Active Movies remux gate:** Pending/leased ``refiner.file.remux_pass.v1`` with **Movies** scope (``media_scope`` missing counts as movie) and the **same normalized** ``relative_media_path`` as this pass blocks cleanup (exclude current job id). **TV** remux jobs never block this pass.
6. **Dry run:** When the **remux pass** is dry-run only, Pass 3a does not run at all (no Radarr read, no output-folder inspection or age gate, no delete/cascade); activity fields record an honest skip. Live Movies remux paths still perform no filesystem mutations until all gates pass, then delete when allowed.
7. **Locks:** ``rmtree`` / ``rmdir`` ``OSError`` — skip folder, log, continue without crashing.
8. **Activity / result:** ``movie_output_folder_deleted``, ``movie_output_folder_path``, ``movie_output_folder_skip_reason``, ``movie_output_truth_check`` (``passed`` / ``failed`` / ``skipped``), ``movie_output_truth_note``, ``movie_output_age_seconds``, ``movie_output_cascade_folders_deleted``, ``movie_output_dry_run``.
9. **Invocation:** Runs **after successful Movies remux pass completion** (dry-run planned, live written, or live skipped-not-required) from ``run_refiner_file_remux_pass`` — not a separate periodic job (output cleanup is tied to the file that was just processed).
10. **Tests** cover truth pass/block, Radarr down, age, active job, TV job non-block, cascade, root==folder skip, lock, remux dry-run early exit (no Radarr), out-of-root guard, activity keys.

### 14 — status

- [x] **Pass 3a shipped** — ``refiner_movie_output_cleanup.py`` (Radarr ``GET /api/v3/movie`` truth gate, min-age env, same-``relative_media_path`` active Movies remux gate, dry-run + lock handling, output-root-bounded cascade), ``refiner_file_remux_pass_run.py`` post-success hook, ``MediaMopSettings`` + runtime snapshot + web Workers copy, ``test_refiner_movie_output_cleanup.py``.

## Roadmap item 15 — Refiner Pass 3b (TV output-folder season / show cleanup)

**Scope (explicit):** **TV only** (``media_scope=tv``). Deletes the **immediate parent folder of the written episode file** (the **season output folder**) under the resolved **TV output root** when all gates pass, then cascades empty parents up to but not including the TV output root. **No** Movies output cleanup, **no** watched-folder Pass 1/1b, **no** work/temp Pass 2, **no** change to Pass 3a.

**Completion criteria (must all be true to tick):**

1. **Non-TV abort:** If ``media_scope`` is not ``tv``, this pass does not run; plain skip reason; **never** calls Sonarr or touches TV output paths.
2. **Root bounds:** Season folder must be strictly under resolved TV output root; never delete the output root; never delete outside the root (``Path.relative_to``).
3. **Sonarr library truth (mandatory):** Before delete, load Sonarr episode files (``GET /api/v3/episodefile``). If **any** episode file ``path`` resolves **inside** the candidate season output folder, **skip** deletion (kept library). Queue membership is **not** the gate. If Sonarr is unreachable or the list cannot be read, **skip** (fail safe).
4. **Minimum age:** Eligible only when the **newest** ``st_mtime`` among **direct-child** Refiner media candidate files in the season folder is older than ``refiner_tv_output_cleanup_min_age_seconds`` (default 48h, env at process start). Do **not** recurse into subfolders for this age decision set.
5. **Active TV remux gate:** Pending/leased ``refiner.file.remux_pass.v1`` with ``media_scope=tv`` whose **expected TV output file path** maps to the **same season output folder** as this pass blocks cleanup (exclude current job id). **Movies** (or missing scope) jobs **never** block TV output cleanup.
6. **Dry run:** When the **remux pass** is dry-run only, Pass 3b does not run at all (no Sonarr read, no output-folder inspection, no delete/cascade); activity fields record an honest skip.
7. **Locks:** ``rmtree`` / ``rmdir`` ``OSError`` — skip folder, log, continue without crashing.
8. **Activity / result:** ``tv_output_season_folder_deleted``, ``tv_output_season_folder_path``, ``tv_output_season_folder_skip_reason``, ``tv_output_truth_check``, ``tv_output_truth_note``, ``tv_output_age_seconds``, ``tv_output_cascade_folders_deleted``, ``tv_output_dry_run``.
9. **Invocation:** Runs **after successful TV remux pass completion** (same outcomes as Pass 3a hook: dry-run planned, live written, live skipped-not-required) from ``run_refiner_file_remux_pass`` — not a separate periodic job.
10. **Tests** cover truth pass/block, Sonarr down, age (direct-child only), active TV job, Movies job non-block, cascade, root==season skip, lock, remux dry-run early exit, out-of-root guard, activity keys, episode set definition.

### 15 — status

- [x] **Pass 3b shipped** — ``refiner_tv_output_cleanup.py`` (Sonarr ``GET /api/v3/episodefile`` truth gate, min-age env on direct-child episode media, same-season-output active **TV** remux gate, remux dry-run early exit, output-root-bounded cascade), ``refiner_file_remux_pass_run.py`` post-success hook after Pass 3a, ``MediaMopSettings`` + runtime snapshot + web Workers copy, ``test_refiner_tv_output_cleanup.py``.

## Roadmap item 16 — Refiner Pass 4 (failure cleanup sweep, per scope)

**Scope (explicit):** Terminal **failed** Refiner remux jobs only (``job_kind=refiner.file.remux_pass.v1``, ``status=failed``). Periodic sweep per scope (Movies vs TV independent) may remove stale failed leftovers under watched/output/work roots when ARR queue truth and scope safety gates allow it. **No** success cleanup behavior changes for Pass 1/1b/2/3a/3b.

**Completion criteria (must all be true to tick):**

1. **Query scope:** Includes only failed remux rows (exclude ``cancelled`` and ``handler_ok_finalize_failed``).
2. **Failure age:** Uses ``updated_at`` as the failure-age timestamp and per-scope grace periods before eligibility.
3. **Per-scope grace settings:** ``MEDIAMOP_REFINER_MOVIE_FAILURE_CLEANUP_GRACE_PERIOD_SECONDS`` and ``MEDIAMOP_REFINER_TV_FAILURE_CLEANUP_GRACE_PERIOD_SECONDS`` (defaults 1800s, clamp 300..604800).
4. **Dry-run jobs:** Failed remux payloads with ``dry_run=true`` are skipped entirely (no filesystem mutation).
5. **ARR boundary:** Movies uses Radarr queue; TV uses Sonarr queue on direct-child episode set; ARR unreachable = skip fail-safe.
6. **TV season-clear rule:** Only remove watched/output season folders when direct-child episode media set is clear (none in Sonarr queue and none pending/leased TV remux for that season target).
7. **Bounds + locks:** Never delete watched/output roots or paths outside resolved roots; lock failures are non-fatal and logged.
8. **Work/temp:** Removes only Refiner-owned temp artifacts attributable to failed jobs in that scope’s work folder.
9. **Invocation shape:** Separate periodic durable cleanup units per scope (independent timing and enqueue state; no shared sweep job).
10. **Activity/result truth:** Per-scope ``*_failure_cleanup_*`` fields in plain language for ran/skip/deleted/queue-check/dry-run/cascade/temp results.
11. **Tests:** Cover eligible cleanup, queue blocks, ARR down skip, dry-run skip, bounds, lock behavior, per-scope grace handling, missing path-settings skip, and Movies/TV independence.

### 16 — status

- [x] **Pass 4 shipped** — dedicated failure sweep job families (`refiner.movie_failure_cleanup_sweep.v1` / `refiner.tv_failure_cleanup_sweep.v1`), per-scope periodic enqueue + grace knobs, failed-row query on `status=failed` + `updated_at` age gate, ARR queue fail-safe boundary checks, dry-run skip, bounded watched/output/temp cleanup with lock-safe behavior, runtime visibility + tests.

## Active / next (ordered)

1. **Fetcher operator surface (item 9 web, continued)** — Iterate tabbed Fetcher UX and copy per open bullets above; keep central Settings pure; extend tests as slices land.
2. **Richer Activity rendering** for watched-folder scan summaries if plain `detail` text is not enough (Refiner-facing polish).
3. **Taxonomy / tree truth (optional):** suite `dashboard` package location, `queue_worker` naming vs role, `arr_failed_import` vs env seam — only when justified by ownership truth.
4. **Backlog:** SQLite WAL mode; SSE/WebSocket or similar push for activity/dashboard; app-wide hard copy pass.

## Completed / deferred reference

- No duplicate task file at repo root; this file remains the milestone canon; Cursor may hold ephemeral execution detail — fold shipped outcomes back here.
