# ADR-0002: Database storage and Alembic (SQLite-first)

## Status

**Accepted**, **amended (Stage 10 — SQLite-first runtime).**

The filename retains `postgresql` for stable links; the **effective** decision is SQLite file storage as described below.

## Context

MediaMop needs durable product state, **SQLAlchemy 2.x**, and **Alembic** for schema evolution. An earlier draft of this ADR assumed **PostgreSQL** as the primary store and **`MEDIAMOP_DATABASE_URL`**.

**Stage 10** locked the product to **SQLite** as the single supported database for `apps/backend`, with explicit filesystem layout under **`MEDIAMOP_HOME`** and related env vars (see **`apps/backend/.env.example`**).

## Decision (effective)

1. **`apps/backend`** persists state in **file-backed SQLite** (path from **`MEDIAMOP_HOME`** / **`MEDIAMOP_DB_PATH`**), not a network database URL.

2. **All schema changes** use **Alembic** (revisions under `apps/backend/alembic/`). Ad hoc `create_all` in production is **not** the desired end state.

3. **Runtime configuration** uses **`MEDIAMOP_HOME`**, **`MEDIAMOP_DB_PATH`**, and sibling directory env vars; **`MEDIAMOP_DATABASE_URL`** is **not** part of the supported foundation.

4. **SQLAlchemy** applies SQLite connection hardening (e.g. WAL, foreign keys, busy timeout) at the engine layer (`mediamop.core.db`).

5. The **Fetcher** application (separate repository) remains independent; this ADR governs **this** repository only.

## Consequences

- Developers run **`alembic upgrade head`** and tests with a writable **`MEDIAMOP_HOME`** (CI uses a temp directory).
- Operators back up the SQLite file and **`MEDIAMOP_HOME`** tree; no Postgres DSN management.

## Compliance

- Do not introduce a parallel ad-hoc migration system under `apps/backend`.
- New models subclass shared **`Base`** and ship with Alembic revisions.

## Current implementation snapshot

- **`mediamop.core.db`**: sync SQLite `Engine` + `sessionmaker`, PRAGMA hooks on connect.
- ORM: **`users`**, **`user_sessions`**, **`activity_events`** via Alembic.
- **`mediamop.core.config`**: resolves paths and builds the SQLite SQLAlchemy URL.

## Historical note

Pre–Stage 10 text in version control described PostgreSQL + **`MEDIAMOP_DATABASE_URL`**; that configuration is **removed** from the supported runtime.
