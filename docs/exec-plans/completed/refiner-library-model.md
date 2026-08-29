# Plan: Refiner library model

## Goal

An operator can configure any number of Refiner libraries — each with its own paths,
admission rules, remux rules, schedule, guardrails and media manager — instead of one
movie folder and one TV folder. Upgrading an existing install changes nothing an
operator can observe until they choose to add a library.

Decision record: [ADR-0014](../../adr/ADR-0014-refiner-libraries-replace-fixed-scopes.md).
Tracking epic: [#347](https://github.com/jampat000/MediaMop/issues/347).

## Current State

- `refiner_path_settings` — singleton row, movie paths plus `refiner_tv_*` duplicates.
- `refiner_remux_rules_settings` — singleton row, ten fields plus `tv_` duplicates.
- `refiner_operator_settings` — global guardrails, per-scope schedule windows.
- `_MEDIA_EXTENSIONS` and `_TRANSIENT_DOWNLOAD_DIR_MARKERS` are module constants.
- `credentials.py` infers the manager from `{"movie": "radarr", "tv": "sonarr"}`.
- `media_scope` is the partition key for the scan dispatch, remux pass, cleanup and
  sweep families.

Baseline at the time of writing: 763 backend tests, 166 web tests, coverage 77.62%
against a 70% CI floor, `alembic check` clean.

## Scope

- `apps/backend/src/mediamop/modules/refiner/` — path, rules and operator settings
  models, services, schemas and APIs; the four job families that resolve configuration.
- `apps/backend/alembic/versions/` — new tables, seed, and a later drop.
- `apps/backend/src/mediamop/platform/media_managers/credentials.py` — retire the
  scope-to-kind inference.
- `apps/web/src/pages/refiner/` and `apps/web/src/lib/refiner/` — Libraries screen.
- `docs/adr/`, `ARCHITECTURE.md`, `docs/settings-truthfulness-audit.md`.

## Non-Goals

- The media manager port and its dialects ([#350]) — a prerequisite, tracked separately.
- Library discovery from a manager ([#351]).
- Any change to Pruner's instance model.
- Any change to preflight probe depth — ADR-0012's boundary is untouched.
- File states, hold timers, watcher, schedules-gate-processing, runner units, retry, and
  per-file logs. All of them sit on top of this and are separately tracked.

## Acceptance Criteria

- An operator can create, edit, reorder, disable and delete a Refiner library.
- A third library processes independently of the seeded two, with its own paths, rules,
  schedule and guardrails.
- After upgrade and before any operator action, Refiner behaves **identically**: same
  folders, same rules, same guardrails, same schedule, same manager.
- Deleting a library with queued or leased jobs is refused with a clear reason.
- Extensions and exclusion markers are editable per library and seeded from today's
  constants.
- A library names its manager connection(s); no code path infers a manager from scope.
- Full CRUD over `/api/v1/refiner/libraries` with OpenAPI regenerated and no drift.
- `pytest -q --cov=mediamop --cov-fail-under=70`, `ruff check src tests`, `mypy src/mediamop`,
  `alembic upgrade head && alembic check`, `npm run lint`, `npm run format`,
  `npm run build`, `npm run test`, `npm run api:types:check` all pass.
- E2E smoke passes.

## Steps

Each step is a PR that leaves `main` releasable.

1. **Prerequisite: media manager port ([#350]).** Refiner stops naming Radarr and Sonarr
   and gains a fan-out port. Lands first because step 5 needs somewhere for a library's
   manager reference to point, and because it is independent of this schema.

2. **Schema and seed.** Add `refiner_libraries` and `refiner_rule_sets`. Migration seeds
   "Movies" and "TV" from the singleton rows, carrying every current value and the two
   module constants as saved defaults. **Nothing reads the new tables yet.** A rollback at
   this point is a table drop.

3. **Read path.** Every family resolves configuration by library instead of by scope,
   still reading only the two seeded rows. No UI, no CRUD. This is the step that proves
   the no-op: the full suite must pass unchanged.

4. **Job payloads.** Add `library_id` alongside `media_scope`, with a payload lacking one
   resolving to the seeded library for its scope. Test a pre-upgrade payload explicitly.

5. **Manager binding.** A library names its connection(s). Retire the scope-to-kind
   inference in `credentials.py`. Migration links the seeded libraries to whatever the
   inference would have chosen.

6. **CRUD and API.** `/api/v1/refiner/libraries` and `/api/v1/refiner/rule-sets`, with
   deletion guards. OpenAPI regenerated.

7. **Libraries screen.** Replaces the current Libraries tab. Add, edit, reorder, enable,
   disable, delete.

8. **Drop the singletons.** A separate migration, only once nothing reads them, so steps
   2 through 7 each have somewhere to roll back to. *Done — `0025`, [#363].* The two
   `/api/v1` surfaces they backed are kept and repointed at the libraries rather than
   removed: the setup wizard writes through path-settings on first run, and the Refiner
   overview reads both.

9. **Docs.** `ARCHITECTURE.md`, `docs/settings-truthfulness-audit.md`, and move this plan
   to `completed/`. *Done.*

## Risks

- **Silent path repointing.** A library's watched folder is the input to source-folder
  deletion. Any migration or edit that changes a path without the operator intending it is
  destructive. Migrations copy values verbatim; edits require explicit save.
- **Coverage floor.** 7.6 points of headroom above the 70% CI floor. Steps 2, 6 and 7 add
  significant code; each PR carries its own tests rather than deferring them.
- **The no-op claim is the whole risk.** Step 3 is where it is proven or lost. If the full
  suite does not pass unchanged there, stop rather than adjusting tests to fit.

## Validation Log

- 2026-08-28 — baseline recorded: 763 backend tests, 166 web tests, coverage 77.62%,
  `alembic check` reports no new upgrade operations, working tree clean at `07c5fab`.
- 2026-08-29 — step 8: 1194 backend tests, 209 web tests, 7 E2E, `alembic check` reports
  no new upgrade operations against a database built from `0001` through `0025`.
- 2026-08-29 — plan complete. All nine steps landed; `main` carries libraries as the only
  Refiner configuration store.

## Decisions

- 2026-08-28 — **Rule sets are a named object, not inline on the library.** Inline is
  simpler for one library, which is the situation this plan exists to end. ADR-0014 §3.
- 2026-08-28 — **`library_id` is an additive payload field, not a new job-kind version.**
  A version bump would strand rows already queued at upgrade, and the queue is where a
  half-finished remux lives. ADR-0014 §5.
- 2026-08-28 — **A library names its manager explicitly; the scope-to-kind inference is
  retired.** It cannot express a manager serving both scopes, which Deluno does.
  ADR-0014 §4.
- 2026-08-28 — **[#350] lands before step 2.** Writing the ADR's manager-binding decision
  against a real port is more reliable than against a planned one, and #350 changes no
  schema so it is a clean first PR.

- 2026-08-29 — **A v3 configuration bundle is translated onto the seeded libraries, not
  rejected.** The alternative strands a backup taken the day before an upgrade, which is
  exactly when one is taken. `BUNDLE_FORMAT_VERSION` is 4 and 3 stays restorable.
- 2026-08-29 — **A stored `subtitle_mode` of `keep_all` is read as keep-selected, not
  migrated to `remove_all`.** It is the rule-set table's server default and never a mode
  anything implements; the planner already read it as keep-selected. Rewriting the stored
  value would start deleting subtitles nobody asked to delete.

[#350]: https://github.com/jampat000/MediaMop/issues/350
[#351]: https://github.com/jampat000/MediaMop/issues/351
[#363]: https://github.com/jampat000/MediaMop/issues/363
