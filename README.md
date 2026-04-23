# MediaMop

<!-- README_LOCKED_SECTION_START: project-note -->
## A note on this project

This is a vibe-coded project.

I am not a software engineer, and I have a lot of respect for the people who do this properly for a living.

I built MediaMop because I could not find something that matched the way I actually wanted to manage my media setup. I needed something opinionated, practical, and built around the workflows I care about, so I kept going until it did what I needed.

Every feature is here because it solved a real problem for me first. The product decisions come from that angle too: user workflow before theory.

If it ends up useful to you as well, use it. If you want to fork it and take it somewhere else, do that.

It was built by someone who just wanted their media library to work properly.

<!-- README_LOCKED_SECTION_END: project-note -->

MediaMop is a standalone product: FastAPI + SQLite backend in `apps/backend` and React + Vite web shell in `apps/web`.

## Screenshots

![Dashboard](screenshots/dashboard.png)

![Activity](screenshots/activity.png)

![Refiner activity detail](screenshots/refiner-activity.png)

## Quick start

Prerequisites:

- Python 3.11+
- Node.js LTS with `npm` on `PATH`

From the repository root:

1. Create the backend virtual environment:

   ```powershell
   cd apps\backend
   py -3 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -e .
   ```

2. Copy `apps/backend/.env.example` to `apps/backend/.env` and set `MEDIAMOP_SESSION_SECRET`.
3. Run migrations:

   ```powershell
   cd ..\..
   .\scripts\dev-migrate.ps1
   ```

4. Start the repo-local dev stack:

   ```powershell
   cd apps\web
   npm ci
   npm run dev
   ```

The default dev URL is `http://localhost:8782/`.

## Runtime notes

- SQLite runtime files live under `MEDIAMOP_HOME`
- production deployments should expose one canonical HTTPS origin
- local development uses the Vite `/api` proxy; keep `VITE_API_BASE_URL` unset unless you know you need it

## Verification

Optional local verification:

```powershell
.\scripts\verify-local.ps1
```

Canonical ports: [`docs/ports.md`](docs/ports.md)

Full local development instructions: [`docs/local-development.md`](docs/local-development.md)

## Releases

Release instructions and artifact types: [`docs/release.md`](docs/release.md)

Current release outputs include:

- GitHub Release on `vX.Y.Z`
- `mediamop-web-dist.zip`
- `MediaMopSetup.exe`
- Docker images on GHCR such as `ghcr.io/jampat000/mediamop:latest`

## Docker

Quick start:

```bash
docker pull ghcr.io/jampat000/mediamop:latest
docker run --rm -p 8788:8788 -v mediamop-data:/data/mediamop ghcr.io/jampat000/mediamop:latest
```

Or from a repo clone:

```bash
docker compose pull
docker compose up -d
```

No env file is required for the default Docker path. The container will generate and persist
its own session secret if you do not provide one.

Full Docker instructions: [`docker/README.md`](docker/README.md)

## Architecture

Locked decisions: [`docs/adr/`](docs/adr/)

Current shipped vs next work: [`docs/TASKS.md`](docs/TASKS.md)

## Transitional Jinja app

An older Jinja/SQLite experiment lived in another repository. It is not part of this tree and is not the active shell. `apps/web` is the UI source of truth.
