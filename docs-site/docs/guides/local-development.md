---
sidebar_position: 1
title: Local Development
---

# Local Development

This guide covers backend and web development setup for Weir.

## Prerequisites

- **Python 3.11+**
- **Node.js LTS** (npm on `PATH`)

The backend uses file-backed SQLite under `WEIR_HOME`. No PostgreSQL required.

## Backend setup

### Environment file

Copy `apps/backend/.env.example` to `apps/backend/.env`. Required variables:

| Variable | Purpose |
|----------|---------|
| `WEIR_SESSION_SECRET` | Signs sessions and CSRF tokens |
| `WEIR_CREDENTIALS_SECRET` | Encrypts saved provider credentials |

Optional path overrides (defaults are under `WEIR_HOME`):

- `WEIR_HOME`, `WEIR_DB_PATH`, `WEIR_BACKUP_DIR`, `WEIR_LOG_DIR`, `WEIR_TEMP_DIR`

### Apply migrations

```powershell
.\scripts\dev-migrate.ps1
```

Or manually:

```powershell
cd apps/backend
$env:PYTHONPATH = "src"
alembic check
alembic upgrade head
```

### Start the API

```powershell
.\scripts\dev-backend.ps1
```

Or manually:

```powershell
cd apps/backend
$env:PYTHONPATH = "src"
$env:WEIR_SESSION_SECRET = "<long random>"
uvicorn weir.api.main:app --host 127.0.0.1 --port 8788 --reload
```

## Web app

```powershell
cd apps/web
npm ci
npm run dev
```

`npm run dev` clears processes on the default dev ports, then starts the API and Vite together.

### OpenAPI type generation

Generate TypeScript API types from the backend OpenAPI schema (no live server needed):

```powershell
cd apps/web
npm run api:types:sync
```

This exports the schema to `apps/web/openapi/weir-openapi.json` and regenerates types at `apps/web/src/lib/api/generated/openapi-types.ts`. Run this whenever backend request/response schemas change.

## Weir home paths

| Platform | Default `WEIR_HOME` |
|----------|------------------------|
| Windows | `%PROGRAMDATA%\Weir` |
| Linux/macOS | `$XDG_DATA_HOME/weir` or `~/.local/share/weir` |

The default SQLite file is `{WEIR_HOME}/data/weir.sqlite3` unless `WEIR_DB_PATH` overrides.

## E2E tests (optional)

Requires Playwright + Chromium:

```powershell
cd apps/web
npm ci
npm run build
cd ../..
$env:WEIR_E2E = "1"
$env:WEIR_SESSION_SECRET = "local-dev-secret-at-least-32-characters-long"
pytest tests/e2e/weir -q --tb=short
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `npm run dev` fails | Install Node.js LTS and open a new terminal |
| Login/setup broken | Use the Vite proxy (same origin); don't set `VITE_API_BASE_URL` |
| "Cannot reach the API" | Check `GET /health` on port 8788; ensure migrations ran |
| SQLite errors | Confirm `.\scripts\dev-migrate.ps1` completed without errors |
| `No module named weir` | Use `PYTHONPATH=src` with cwd `apps/backend` |
| Port already in use | See `scripts/dev-ports.json` for defaults |
