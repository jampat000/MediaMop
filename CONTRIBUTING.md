# Contributing — MediaMop

This repository is **MediaMop** (`apps/backend` + `apps/web`).

## Workflow

Use short-lived branches and open pull requests into `main`. Keep CI green before merge.

## Local checks

**Backend unit tests** (SQLite — `tests/conftest.py` sets an isolated temp **`MEDIAMOP_HOME`** for the session):

```powershell
cd apps/backend
$env:PYTHONPATH = "src"
$env:MEDIAMOP_SESSION_SECRET = "local-dev-secret-at-least-32-characters-long"
python -m pip install -e ".[dev]"
pytest -q
```

**Web** (from repo root; `package-lock.json` is committed — prefer reproducible installs):

```powershell
cd apps/web
npm ci
npm run build
npm run test
```

**Optional E2E** (SQLite temp home + Playwright Chromium + built web):

```powershell
python -m pip install playwright
python -m playwright install chromium
cd apps/web
npm ci
npm run build
cd ../..
$env:MEDIAMOP_E2E = "1"
$env:MEDIAMOP_SESSION_SECRET = "local-dev-secret-at-least-32-characters-long"
pytest tests/e2e/mediamop -q --tb=short
```

See **[`docs/local-development.md`](docs/local-development.md)** for env layout and CI parity.

## Security

Do **not** commit `.env`, real secrets, or production database paths. Use `.env.example` patterns only.
