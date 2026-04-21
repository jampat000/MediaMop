# Architecture Decision Records — MediaMop

ADRs in this folder capture **locked** structural and platform choices for this repository. They override ad hoc experimentation when the two conflict.

**Durable-job timing:** operator-controlled intervals, schedules, cooldowns, retries, last-run, and timing-based pruning must follow [ADR-0009](ADR-0009-suite-wide-timing-isolation.md) (per module, then per job family).

**Numbering:** [ADR-0004](ADR-0004-reserved-number.md), [ADR-0005](ADR-0005-reserved-number.md), and [ADR-0006](ADR-0006-reserved-number.md) are intentionally reserved (no architectural body) so filenames and cross-references stay stable. **Git rename noise** around the large Fetcher lane migration is documented in [note-git-rename-metadata-93547e2.md](note-git-rename-metadata-93547e2.md); fixing it would require history rewrite and force-push.

| ADR | Title |
|-----|--------|
| [ADR-0001](ADR-0001-repo-structure.md) | Repository and application layout |
| [ADR-0002](ADR-0002-database-sqlite-alembic.md) | Database and Alembic (SQLite-first) |
| [ADR-0003](ADR-0003-auth-session-model.md) | Auth and session model |
| [ADR-0004](ADR-0004-reserved-number.md) | Reserved number (no document) |
| [ADR-0005](ADR-0005-reserved-number.md) | Reserved number (no document) |
| [ADR-0006](ADR-0006-reserved-number.md) | Reserved number (no document) |
| [ADR-0007](ADR-0007-module-owned-worker-lanes.md) | Module-owned worker lanes (SQLite) |
| [ADR-0008](ADR-0008-mediamop-settings-aggregate-runtime-config.md) | `MediaMopSettings` aggregate for runtime configuration |
| [ADR-0009](ADR-0009-suite-wide-timing-isolation.md) | Suite-wide timing isolation (durable work) |
| [ADR-0010](ADR-0010-fetcher-failed-import-taxonomy-contract.md) | Fetcher failed-import taxonomy contract |
| [ADR-0011](ADR-0011-fetcher-failed-import-upstream-queue-delete-contract.md) | Fetcher upstream queue delete contract |
| [ADR-0012](ADR-0012-refiner-preflight-parity-boundary.md) | Refiner preflight parity boundary (FileFlows-aligned) |
