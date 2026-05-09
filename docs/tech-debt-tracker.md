# Tech Debt Tracker

This file tracks known follow-up items that were intentionally deferred from `hardening/code-quality-pass-1`.

## P1 — Mypy coverage gaps in legacy modules

- **File/context:** `apps/backend/pyproject.toml` (`[[tool.mypy.overrides]]`)
- **Issue:** `mediamop.modules.refiner.*` and `mediamop.windows.*` are temporarily excluded from stricter mypy checks.
- **Suggested fix:** Remove overrides incrementally by fixing module-local typing debt (module export typing, legacy dynamic dict payloads, and Windows process-state typing).
- **Reason deferred:** High churn/risk areas; this pass intentionally avoided broad updater/refiner rewrites.

## P2 — Ruff rule families deferred to avoid high-churn rewrites

- **File/context:** `apps/backend/pyproject.toml` (`[tool.ruff.lint]`)
- **Issue:** `I` (isort), `UP` (pyupgrade), and `SIM` (simplify) were evaluated but not enabled globally.
- **Suggested fix:** Enable one family at a time with dedicated cleanup PRs and ownership boundaries.
- **Reason deferred:** Current repo produces high-volume churn for these families; would bloat this hardening pass.

## P2 — Remaining targeted `type: ignore` comments

- **File/context:** `apps/backend/src/mediamop/windows/tray_app.py:240`, multiple `apps/backend/src/mediamop/modules/refiner/*` locations, `apps/backend/src/mediamop/platform/auth/router.py:116`, `:302`
- **Issue:** Existing ignores are still required for platform-specific/runtime edge typing and legacy payload shims.
- **Suggested fix:** Replace ignores with typed wrappers/protocols and narrowed helper return types in module-specific PRs.
- **Reason deferred:** Most are in Windows/refiner scopes intentionally out-of-scope for this pass.

## P2 — Storage-savings metrics not yet exposed

- **File/context:** `apps/backend/src/mediamop/platform/metrics/service.py` and module-specific result handlers
- **Issue:** Runtime metrics now expose module job counters and queue depth gauges, but not durable storage-savings totals.
- **Suggested fix:** Emit explicit savings events from canonical module completion paths (Refiner output writes, Pruner removals) and aggregate in metrics service.
- **Reason deferred:** Savings values are not consistently surfaced in a single trusted result contract across all handlers yet.

## P2 — OpenAPI TypeScript contract generation workflow

- **File/context:** `apps/web` build/scripts (no committed typegen workflow yet)
- **Issue:** Frontend does not currently use generated OpenAPI TS contracts.
- **Suggested fix:** Add a dedicated generation script (e.g., `openapi-typescript`) that reads a pinned OpenAPI artifact (committed JSON or CI-produced artifact), plus CI drift check.
- **Reason deferred:** Need to avoid coupling normal frontend dev/build to a live backend and decide artifact ownership.
