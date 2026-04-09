# Architecture Decision Records — MediaMop

ADRs in this folder capture **locked** structural and platform choices for this repository. They override ad hoc experimentation when the two conflict.

| ADR | Title |
|-----|--------|
| [ADR-0001](ADR-0001-repo-structure.md) | Repository and application layout |
| [ADR-0002](ADR-0002-database-postgresql-alembic.md) | PostgreSQL and Alembic |
| [ADR-0003](ADR-0003-auth-session-model.md) | Auth and session model |

The **Fetcher** application (separate repository) may remain the operational reference for legacy behavior until features are deliberately reimplemented here; that does **not** make this repo a copy of Fetcher.
