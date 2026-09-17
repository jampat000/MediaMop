# ADR-0001: Repository and application layout

## Status

Accepted — Weir standalone repository (extracted from shared-history monorepo, 2026).

## Context

Weir is its **own product** and **own Git repository**. The backend and web shell are developed together here. Earlier prototype stacks are **not** carried forward as the primary architecture.

## Decision

1. **Canonical product code** lives under:
   - **`apps/backend/`** — FastAPI application package, Alembic, domain layout (`weir` Python package under `src/`).
   - **`apps/web/`** — Vite + React + TypeScript UI shell.

2. **Python import root** for the backend is the package **`weir`** under `apps/backend/src/weir/` with subpackages:
   - `core` — foundational types, DB Base, shared config helpers (no product workflows).
   - `platform` — cross-cutting product infrastructure (auth, settings, health, etc.).
   - `modules` — user-facing capabilities (when implemented).
   - `integrations` — external systems (when implemented).
   - `api` — HTTP app factory, routers, wiring.

3. **Documentation** for structural intent lives in **`docs/adr/`** and this repository’s **README**.

4. **HTTP routing convention:** operational **`GET /health`** stays at the **app root**. Versioned **JSON product APIs** use the prefix **`/api/v1`**, composed via `weir.api.router`.

## Consequences

- **CI** validates `apps/backend`, `apps/web`, and optional E2E under **`tests/e2e/weir/`** only in **this** repository.
- **No** third-party application packages are vendored into the runtime tree; product code lives under `weir` and `apps/web` only.

## Compliance

- **No** cross-repository business-logic migration is implied by this ADR alone; slices are explicit, separate efforts.
