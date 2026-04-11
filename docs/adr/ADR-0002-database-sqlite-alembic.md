# ADR-0002: Database storage and Alembic (SQLite-first monorepo)

## Status

**Accepted.** This repository’s backend (`apps/backend`) is the source of truth for persistence described here.

## Context

MediaMop needs durable product state, **SQLAlchemy 2.x**, and **Alembic** for schema evolution. Early drafts considered **PostgreSQL** and **`MEDIAMOP_DATABASE_URL`**; that path is **not** supported.

The **MediaMop** product in this monorepo includes the FastAPI backend and the Vite web app under `apps/web`. A separate “Fetcher-only” repository is **not** required for this ADR to apply.

## Decision

1. **`apps/backend`** persists state in **file-backed SQLite** (path from **`MEDIAMOP_HOME`** / **`MEDIAMOP_DB_PATH`**), not a network database URL.

2. **All schema changes** use **Alembic** (revisions under `apps/backend/alembic/`). Ad hoc `create_all` in production is **not** the desired end state.

3. **Runtime configuration** uses **`MEDIAMOP_HOME`**, **`MEDIAMOP_DB_PATH`**, and sibling directory env vars; **`MEDIAMOP_DATABASE_URL`** is **not** part of the supported foundation.

4. **SQLAlchemy** applies SQLite connection hardening (WAL, foreign keys, busy timeout) at the engine layer (`mediamop.core.db`).

## Consequences

- Developers run **`alembic upgrade head`** and tests with a writable **`MEDIAMOP_HOME`** (CI uses a temp directory).
- Operators back up the SQLite file and **`MEDIAMOP_HOME`** tree; no Postgres DSN management.

## Compliance

- Do not introduce a parallel ad-hoc migration system under `apps/backend`.
- New models subclass shared **`Base`** and ship with Alembic revisions.

## Current implementation snapshot

- **`mediamop.core.db`**: sync SQLite `Engine` + `sessionmaker`, PRAGMA hooks on connect.
- ORM tables include **`users`**, **`user_sessions`**, **`activity_events`**, module-owned job tables (e.g. **`refiner_jobs`**, **`fetcher_jobs`**) via Alembic.
- **`mediamop.core.config`**: resolves paths and builds the SQLite SQLAlchemy URL.

## Historical note

Older filenames and text referred to PostgreSQL; the **supported** store for this repo is **SQLite** only.
