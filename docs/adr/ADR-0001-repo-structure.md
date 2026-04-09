# ADR-0001: Repository and application layout

## Status

Accepted — MediaMop standalone repository (extracted from shared-history monorepo, 2026).

## Context

MediaMop is its **own product** and **own Git repository**. The backend and web shell are developed together here. The **Fetcher** application exists in a **different repository** and is not part of this tree.

Historical note: an experimental Jinja/SQLite package once lived alongside Fetcher; it was **never** the long-term architecture. **Do not** reintroduce that stack as the primary product path.

## Decision

1. **Canonical product code** lives under:
   - **`apps/backend/`** — FastAPI application package, Alembic, domain layout (`mediamop` Python package under `src/`).
   - **`apps/web/`** — Vite + React + TypeScript UI shell.

2. **Python import root** for the backend is the package **`mediamop`** under `apps/backend/src/mediamop/` with subpackages:
   - `core` — foundational types, DB Base, shared config helpers (no product workflows).
   - `platform` — cross-cutting product infrastructure (auth, settings, health, etc.).
   - `modules` — user-facing capabilities (when implemented).
   - `integrations` — external systems (when implemented).
   - `api` — HTTP app factory, routers, wiring.

3. **Documentation** for structural intent lives in **`docs/adr/`** and this repository’s **README**.

4. **HTTP routing convention:** operational **`GET /health`** stays at the **app root**. Versioned **JSON product APIs** use the prefix **`/api/v1`**, composed via `mediamop.api.router`.

## Consequences

- **CI** validates `apps/backend`, `apps/web`, and optional E2E under **`tests/e2e/mediamop/`** only in **this** repository.
- **No Fetcher imports** — this codebase does not bundle the Fetcher `app/` package.

## Compliance

- **No** Fetcher business-logic migration is implied by this ADR alone; slices are explicit, separate efforts.
