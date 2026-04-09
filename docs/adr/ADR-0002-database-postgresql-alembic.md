# ADR-0002: PostgreSQL and Alembic

## Status

Accepted.

## Context

Fetcher today uses **SQLite** with an internal migration mechanism. The MediaMop target platform uses **PostgreSQL** as the **canonical** primary database, **SQLAlchemy 2.x**, and **Alembic** for all MediaMop schema changes. SQLite is not the long-term primary store for the suite.

## Decision

1. **MediaMop backend** (`apps/backend`) uses **PostgreSQL** for persistent product state.

2. **All schema changes** for the **`mediamop`** application use **Alembic** exclusively (revision chain under `apps/backend/alembic/versions/`). Ad hoc `create_all` in production for MediaMop is **not** the desired end state.

3. **Database URL** for tooling and runtime is supplied via configuration (environment), for example:
   - **`MEDIAMOP_DATABASE_URL`** — SQLAlchemy URL, e.g. `postgresql+psycopg://user:password@host:5432/mediamop`.
   - Alembic may read the same variable in `env.py` when present, falling back to `alembic.ini` only for local developer convenience.

4. The **Fetcher** application (separate repository) remains on **SQLite**; this ADR does not require changes to that codebase.

## Consequences

- Developers need a local or containerized **Postgres** instance to run migrations and integration tests.
- Operators may run **Fetcher (SQLite)** and **MediaMop (Postgres)** side by side as distinct deployments; they do not share this repository.

## Compliance

- Do not introduce a parallel ad-hoc migration system under `apps/backend`.
- New models must subclass the shared **`Base`** and be registered through Alembic autogenerate or explicit migrations as the team standardizes.

## Current implementation snapshot

- **`mediamop.core.db`** uses a sync `Engine` + `sessionmaker` with naming conventions on `Base`.
- ORM tables include `users`, `user_sessions`, and `activity_events`, managed by Alembic revisions in `apps/backend/alembic/versions/`.
- When `MEDIAMOP_DATABASE_URL` is unset, the app starts and DB-dependent routes return **503**.
