# MediaMop Architecture

This is the top-level map for agents and contributors. Deeper decisions live in [`docs/adr/`](docs/adr/).

## Product Shape

MediaMop is a self-hosted media operations app:

- **Refiner** remuxes watched media into cleaner outputs.
- **Pruner** previews and removes media from connected media servers.
- **Subber** syncs Sonarr/Radarr libraries and manages subtitle coverage.
- **Dashboard, Activity, and Settings** expose runtime health, history, logs, backups, upgrades, and security posture.

## Runtime Shape

- Backend: FastAPI, SQLite, Alembic, Python package under `apps/backend/src/mediamop`.
- Frontend: React + Vite under `apps/web/src`.
- Packaging: Docker and Windows installer workflows.
- Runtime data: `MEDIAMOP_HOME`.

## Backend Map

- `mediamop.api`: FastAPI app factory, router composition, request dependencies.
- `mediamop.core`: config, runtime paths, database setup, lifespan, logging, schema revision checks.
- `mediamop.platform`: shared product services such as auth, activity, jobs, local browse, settings, observability, and suite settings.
- `mediamop.modules`: module-owned domains for Refiner, Pruner, Subber, and Dashboard.
- `mediamop.integrations`: external service integration code.
- `mediamop.windows`: Windows tray and package-specific helpers.

## Frontend Map

- `src/app`: app-level router and providers.
- `src/layouts`: shell/navigation layout.
- `src/pages`: feature pages by module.
- `src/lib`: API clients, query hooks, typed data helpers, and UI helpers.
- `src/components`: reusable UI and brand components.
- `src/styles`: design tokens and shell styling.
- `src/test`: frontend test setup.

## Boundary Rules

- Module code should keep destructive or irreversible behavior behind explicit services and tests.
- Backend APIs should expose typed schemas at boundaries instead of inferred shapes.
- Frontend pages should use typed API/query helpers from `src/lib` rather than ad hoc fetch calls.
- Cross-cutting runtime concerns belong in `mediamop.platform` or `mediamop.core`, not inside module implementation details.
- File lifecycle changes must preserve the safety contract in [`docs/file-lifecycle-contract.md`](docs/file-lifecycle-contract.md).

## Architecture Decision Records

Current ADR index: [`docs/adr/README.md`](docs/adr/README.md).

Add an ADR when a decision changes module ownership, runtime storage, data safety, security boundaries, release mechanics, or packaging behavior.
