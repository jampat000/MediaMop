# Contributing - MediaMop

MediaMop is a self-hosted media workflow app with a FastAPI + SQLite backend in `apps/backend` and a React + Vite web shell in `apps/web`.

## Workflow

Use short-lived branches and open pull requests into `main`. Keep CI green before merge.

## Local checks

Backend unit tests. `tests/conftest.py` sets an isolated temporary `MEDIAMOP_HOME` for the session.

```powershell
cd apps/backend
$env:PYTHONPATH = "src"
$env:MEDIAMOP_SESSION_SECRET = "local-dev-secret-at-least-32-characters-long"
python -m pip install -e ".[dev]"
alembic upgrade head
pytest -q
```

CI runs `alembic upgrade head` before `pytest` in `apps/backend`; include it locally if migrations are ahead of your SQLite file.

Web checks from the repo root. `package-lock.json` is committed, so prefer reproducible installs.

```powershell
cd apps/web
npm ci
npm run build
npm run test
```

Optional E2E checks use a temporary SQLite home, Playwright Chromium, and the built web app.

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

See `docs/local-development.md` for env layout and CI parity.

Remote Docker validation does not require local Docker Desktop:

```powershell
.\scripts\verify-docker-remote.ps1
```

This triggers the GitHub `Test` workflow for the current ref and watches it. The Docker build and smoke test run on GitHub-hosted runners.

## Security

Do not commit `.env`, real secrets, production database files, logs, backups, or machine-specific media paths. Use `.env.example` patterns only.

## License

By contributing to MediaMop, you agree that your contribution is provided under the repository license: AGPL-3.0-or-later.
