# ADR-0008: `MediaMopSettings` as a single aggregate for runtime configuration

## Status

**Accepted** for the current codebase size. This documents an intentional coupling tradeoff, not an accidental omission.

> **Update (2026-08-28): Subber moved to Deluno.** This ADR is left as it was written — an ADR records the decision, not the current file list — but wherever it names Subber, read it as an example rather than as a lane that still exists. The ``subber_jobs`` table is dropped by migration ``0010_drop_subber_tables``, and ``subber.`` is now an abandoned prefix refused on every remaining lane, alongside ``trimmer.``.

## Context

`MediaMopSettings` (`mediamop.core.config`) is a frozen dataclass loaded once at process start. It mixes concerns that belong to different product areas: HTTP/session security, SQLite paths, CORS, and **Refiner / Pruner / Subber** worker counts plus shared *arr* HTTP defaults and Refiner-side schedule toggles.

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
   - **Not tolerated:** modules importing each other’s internals to “reach” settings; new cross-module env prefixes without ADR updates; silent fallback between legacy and current env namespaces (explicit migration only).
   - **Radarr/Sonarr HTTP URL+key:** callers use `MediaMopSettings.arr_http_radarr_credentials()` / `arr_http_sonarr_credentials()` which read the neutral `MEDIAMOP_ARR_{RADARR|SONARR}_*` pair (see SQLite-backed operator settings in `arr_library_operator_settings` for overrides at runtime where implemented).

5. **Relation to module-owned worker lanes**
   - ADR-0007 owns **where durable jobs live** and **which worker pool** runs them. `MediaMopSettings` owns **how many Refiner / Pruner / Subber workers** the process starts and **which ARR endpoints** in-process work may call. That is orthogonal composition: lanes are data-plane tables; settings are control-plane env.

6. **Shared neutral `MEDIAMOP_ARR_*` Radarr/Sonarr credentials**
   - Operators set `MEDIAMOP_ARR_RADARR_BASE_URL`, `MEDIAMOP_ARR_RADARR_API_KEY`, `MEDIAMOP_ARR_SONARR_BASE_URL`, and `MEDIAMOP_ARR_SONARR_API_KEY` as the **default** shared upstream for code that needs a Radarr/Sonarr HTTP base URL and API key together when the database row does not supply a usable pair.

7. **Automatic *arr* search timing**
   - Missing/upgrade search schedules and lane toggles are **database-backed** on `arr_library_operator_settings` (not duplicated as long-lived env mirrors on `MediaMopSettings` at head).
   - Cross-lane timing contracts (no shared cooldowns, schedules, or pruning between unrelated families) are **locked in [ADR-0009](ADR-0009-suite-wide-timing-isolation.md)**.

8. **Why `platform/settings` is not the owner of module-specific runtime config today**
   - There is no separate `platform/settings` package providing a plugin registry; `mediamop.core.config` *is* the platform seam today.
   - Moving keys into hypothetical `platform/settings` without changing the load contract would be a file shuffle, not looser coupling.
   - When triggers in §3 fire, prefer **explicit per-module dataclasses** composed into `MediaMopSettings` (constructor injection from a small number of loaders) over a dynamic plugin map unless multiple deployable binaries appear.

## Related

- [ADR-0009](ADR-0009-suite-wide-timing-isolation.md) — suite-wide timing isolation for durable job families.

## Consequences

- New env vars for Refiner / Pruner / Subber still land in `MediaMopSettings` until this ADR is superseded.
- Documentation and tests should name **retired** env keys explicitly when behavior depends on migration from an older layout.

## Compliance

- Do not add a parallel settings singleton.
- If splitting, add a superseding ADR that names the new loader composition and migration steps for operators.
