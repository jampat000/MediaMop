# ADR-0002: PostgreSQL and Alembic

## Status

Accepted — Phase 1 spine (2026-04-05).

## Context

Fetcher today uses **SQLite** with an internal migration mechanism. The MediaMop target platform uses **PostgreSQL** as the **canonical** primary database, **SQLAlchemy 2.x**, and **Alembic** for all MediaMop schema changes. SQLite is not the long-term primary store for the suite.

## Decision

1. **MediaMop backend** (`apps/backend`) uses **PostgreSQL** for all persistent product state managed by the new spine.

2. **All schema changes** for the **`mediamop`** application use **Alembic** exclusively (revision chain under `apps/backend/alembic/versions/`). Ad hoc `create_all` in production for MediaMop is **not** the desired end state.

3. **Database URL** for tooling and runtime is supplied via configuration (environment), for example:
   - **`MEDIAMOP_DATABASE_URL`** — SQLAlchemy URL, e.g. `postgresql+psycopg://user:password@host:5432/mediamop`.
   - Alembic may read the same variable in `env.py` when present, falling back to `alembic.ini` only for local developer convenience.

4. The **Fetcher** application (separate repository) remains on **SQLite**; this ADR does **not** require changing that codebase.

5. **Phase 1** adds only foundation files: `alembic.ini`, `alembic/env.py`, an empty `versions/` directory, and a shared declarative **`Base`** in `mediamop.core.db` for future models—**no** production tables yet beyond what a no-op or initial revision requires.

## Consequences

- Developers need a local or containerized **Postgres** instance to run migrations and integration tests against the new spine once models exist.
- Operators may run **Fetcher (SQLite)** and **MediaMop (Postgres)** side by side as distinct deployments; they do not share this repository.

## Compliance

- Do not introduce a parallel ad-hoc migration system under `apps/backend`.
- New models must subclass the shared **`Base`** and be registered through Alembic autogenerate or explicit migrations as the team standardizes.

## Compliance — Phase 4 (real)

- **`mediamop.core.db`**: sync `Engine` + `sessionmaker`, naming convention on `Base`, no `create_all` for production paths.
- **ORM**: `users` and `user_sessions` (platform auth) with Alembic revision **`0001_initial_auth`** — **PostgreSQL-oriented** (UUID type for session id).
- **Runtime**: `MEDIAMOP_DATABASE_URL` unset → app starts, `get_db_session` returns **503** for routes that require a DB (health unchanged).
