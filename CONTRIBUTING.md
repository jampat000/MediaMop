# Contributing — MediaMop

This repository is **MediaMop** (`apps/backend` + `apps/web`).

## Workflow

Use short-lived branches and open pull requests into `main`. Keep CI green before merge.

## Local checks

**Backend unit tests** (PostgreSQL required):

```powershell
cd apps/backend
$env:PYTHONPATH = "src"
# Native PostgreSQL (typical local port 5432) — adjust user/password/db:
$env:MEDIAMOP_DATABASE_URL = "postgresql+psycopg://USER:PASS@127.0.0.1:5432/mediamop"
# Optional: if you use repo docker-compose.yml for Postgres only, host port is 5433 instead of 5432.
$env:MEDIAMOP_SESSION_SECRET = "local-dev-secret-at-least-32-characters-long"
python -m pip install -e ".[dev]"
alembic upgrade head
pytest -q
```

**Web** (from repo root; `package-lock.json` is committed — prefer reproducible installs):

```powershell
cd apps/web
npm ci
npm run build
npm run test
```

**Optional E2E** (Postgres + Playwright Chromium + built web):

```powershell
python -m pip install playwright
python -m playwright install chromium
cd apps/web
npm ci
npm run build
cd ../..
$env:MEDIAMOP_E2E = "1"
$env:MEDIAMOP_DATABASE_URL = "postgresql+psycopg://..."
$env:MEDIAMOP_SESSION_SECRET = "local-dev-secret-at-least-32-characters-long"
pytest tests/e2e/mediamop -q --tb=short
```

See **[`docs/local-development.md`](docs/local-development.md)** for **Windows native PostgreSQL**, optional Docker for dev, and CI parity.

## Security

Do **not** commit `.env`, real secrets, or production database URLs. Use `.env.example` patterns only.
