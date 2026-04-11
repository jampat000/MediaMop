# ADR-0008: `MediaMopSettings` as a single aggregate for runtime configuration

## Status

**Accepted** for the current codebase size. This documents an intentional coupling tradeoff, not an accidental omission.

## Context

`MediaMopSettings` (`mediamop.core.config`) is a frozen dataclass loaded once at process start. It already mixes concerns that belong to different product areas: HTTP/session security, SQLite paths, CORS, **Fetcher** HTTP endpoints and worker counts, **Refiner** worker counts, and **ARR failed-import** cleanup policy + drive schedules (via `FailedImportCleanupSettingsBundle`).

Module-owned worker lanes (see [ADR-0007](ADR-0007-module-owned-worker-lanes.md)) place **enqueue, claim, and handlers** in module packages. That does **not** require every env var to be parsed inside those modules today.

## Decision

1. **Keep one aggregate settings object** at the FastAPI process boundary. Workers and routes receive `MediaMopSettings` (or slices derived at call sites) instead of introducing a second global settings registry in this pass.

2. **Why this is acceptable now**
   - One deployment = one backend process reading one SQLite file; configuration cardinality is low (dozens of keys, not hundreds).
   - Startup remains deterministic: a single `MediaMopSettings.load()` validates env and builds derived URLs/paths once.
   - Tests already monkeypatch env and reload settings in focused suites; splitting files without splitting the load seam would not reduce real coupling.

3. **Trigger to split by module or concern**
   - **Volume:** env surface or derived fields grow enough that `config.py` is hard to review or merge-conflict-heavy *and* modules need independent versioning of their config schema.
   - **Ownership:** a module must load or hot-reload its runtime config independently of the API process (not true while everything is in-process SQLite + monolith).
   - **Security boundary:** secrets or operator-only config must be isolated in a different file/process boundary (not required today beyond existing session secrets).

4. **Coupling rules**
   - **Tolerated:** module packages reading **already-parsed** values from `MediaMopSettings` passed in from lifespan or route factories; module-owned **defaults** expressed next to the module but **wired** in `MediaMopSettings.load()` until a split happens.
   - **Not tolerated:** modules importing each other’s internals to “reach” settings; new cross-module env prefixes without ADR updates; silent fallback between `MEDIAMOP_REFINER_*` and `MEDIAMOP_FAILED_IMPORT_*` style namespaces (explicit migration only).

5. **Relation to module-owned worker lanes**
   - ADR-0007 owns **where durable jobs live** and **which worker pool** runs them. `MediaMopSettings` owns **how many Fetcher/Refiner workers** the process starts and **which ARR endpoints** those workers call. That is orthogonal composition: lanes are data-plane tables; settings are control-plane env.

6. **Fetcher Arr search keys on `MediaMopSettings`**
   - Missing/upgrade search for Sonarr and Radarr use **four distinct field groups** on the aggregate (`fetcher_*_{missing|upgrade}_search_*` for max batch, retry delay minutes, schedule window fields).
   - Legacy `MEDIAMOP_FETCHER_SONARR_SEARCH_*` / `MEDIAMOP_FETCHER_RADARR_SEARCH_*` environment variables are read **only** inside `MediaMopSettings.load()` when a lane-specific env key is absent. They supply **defaults** at load time; they do **not** create one shared dataclass field serving two lanes at runtime.
   - Cross-lane timing contracts (no shared cooldowns, schedules, or pruning between families) are **locked in [ADR-0009](ADR-0009-suite-wide-timing-isolation.md)**.

7. **Why `platform/settings` is not the owner of module-specific runtime config today**
   - There is no separate `platform/settings` package providing a plugin registry; `mediamop.core.config` *is* the platform seam today.
   - Moving keys into hypothetical `platform/settings` without changing the load contract would be a file shuffle, not looser coupling.
   - When triggers in §3 fire, prefer **explicit per-module dataclasses** composed into `MediaMopSettings` (constructor injection from a small number of loaders) over a dynamic plugin map unless multiple deployable binaries appear.

## Related

- [ADR-0009](ADR-0009-suite-wide-timing-isolation.md) — suite-wide timing isolation for durable job families.

## Consequences

- New env vars for Fetcher/Refiner/failed-import still land in `MediaMopSettings` until this ADR is superseded.
- Documentation and tests should name **retired** env keys in one place (see `tests/legacy_refiner_failed_import_env_poison.py`) so migrations stay auditable.

## Compliance

- Do not add a parallel settings singleton.
- If splitting, add a superseding ADR that names the new loader composition and migration steps for operators.
