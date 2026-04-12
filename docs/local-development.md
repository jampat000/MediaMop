# MediaMop — local development (backend + web)

This **MediaMop** repository contains **`apps/backend`** (FastAPI, **SQLite**, cookie sessions) and **`apps/web`** (React/Vite). It does **not** include the legacy external **Fetcher** application or that product’s Docker stack; it **does** include the first-party **Fetcher module and UI** inside MediaMop (`mediamop.modules.fetcher`, Fetcher routes under `/api/v1/fetcher/...`, and the Fetcher dashboard in the web app).

**Local web/API ports** are versioned in **`scripts/dev-ports.json`**; the policy is summarized in **[`docs/ports.md`](ports.md)**.

## Prerequisites

- **Python 3.11+**
- **Node.js LTS** (npm on `PATH`)

The backend persists state in **file-backed SQLite** under **`MEDIAMOP_HOME`** (see **`apps/backend/.env.example`**). You do **not** install or run PostgreSQL for normal MediaMop development.

## Backend `.env` (local)

Copy **`apps/backend/.env.example`** → **`apps/backend/.env`**.

Required for auth and `/api/v1`:

- **`MEDIAMOP_SESSION_SECRET`** — long random value.

Optional path overrides (defaults are under the OS-specific **`MEDIAMOP_HOME`**):

- **`MEDIAMOP_HOME`**, **`MEDIAMOP_DB_PATH`**, **`MEDIAMOP_BACKUP_DIR`**, **`MEDIAMOP_LOG_DIR`**, **`MEDIAMOP_TEMP_DIR`**

The API and **Alembic** load **`apps/backend/.env`** automatically; shell variables still override.

## Apply migrations

From repo root:

```powershell
.\scripts\dev-migrate.ps1
```

Or manually:

```powershell
cd apps/backend
$env:PYTHONPATH = "src"
alembic upgrade head
```

## Backend API (manual)

```powershell
cd apps/backend
$env:PYTHONPATH = "src"
$env:MEDIAMOP_SESSION_SECRET = "<long random>"
# $env:MEDIAMOP_CORS_ORIGINS = "http://127.0.0.1:8782"
uvicorn mediamop.api.main:app --host 127.0.0.1 --port 8788 --reload
```

Prefer **`.\scripts\dev-backend.ps1`** from the repo root (uses **`scripts/dev-ports.json`**).

## Web app

```powershell
cd apps/web
npm ci
npm run dev
```

The Vite dev server and **`vite preview`** use **[`scripts/dev-ports.json`](../scripts/dev-ports.json)**. See **[`docs/ports.md`](ports.md)**. To override temporarily, set **`VITE_DEV_API_PROXY_TARGET`** and **`MEDIAMOP_DEV_API_PORT`** together.

## MediaMop home (product paths)

On-disk runtime defaults must **not** be tied to “the Git clone directory” or the process current working directory.

- **`MEDIAMOP_HOME`** (optional): explicit absolute root for product-owned data. Loaded into `MediaMopSettings.mediamop_home`.
- **Default when unset:**
  - **Windows:** `%LOCALAPPDATA%\MediaMop`
  - **Linux/macOS:** `$XDG_DATA_HOME/mediamop`, or `~/.local/share/mediamop`

The default SQLite file is **`{MEDIAMOP_HOME}/data/mediamop.sqlite3`** unless **`MEDIAMOP_DB_PATH`** overrides.

**Linux containers:** set `MEDIAMOP_HOME` to a volume mount (e.g. `/var/lib/mediamop`) so data survives restarts.

## CI validation

The **`Test`** workflow (`.github/workflows/ci.yml`):

1. Runs **`apps/backend`** tests with **`MEDIAMOP_HOME`** on the runner temp dir, **`alembic upgrade head`**, then **`pytest`** (no Postgres service).
2. Runs **`npm ci` → `npm run build` → `npm run test`** in **`apps/web`**.
3. Runs **E2E** with **`MEDIAMOP_E2E=1`**, **`MEDIAMOP_HOME`** on a temp dir, uvicorn + **`vite preview`** + Playwright (from repo-root **`tests/e2e/mediamop/`**, same as local optional E2E below).

Pushing a semver tag **`v*`** runs the **`Release`** workflow, which repeats the same three stages before publishing a GitHub Release — see **[`docs/release.md`](release.md)**.

## E2E (local, optional)

Requires: Playwright + Chromium, Node/npm, built web shell.

```powershell
cd apps/web
npm ci
npm run build
cd ../..
$env:MEDIAMOP_E2E = "1"
$env:MEDIAMOP_SESSION_SECRET = "local-dev-secret-at-least-32-characters-long"
pytest tests/e2e/mediamop -q --tb=short
```

Optional: **`MEDIAMOP_E2E_HOME`** for a fixed data directory; otherwise a temp directory is used (see **`tests/e2e/mediamop/conftest.py`**).

## Split-origin production (deferred wiring)

If the static site and API are on **different origins**:

- Use **HTTPS** everywhere.
- Set **`MEDIAMOP_CORS_ORIGINS`** (and **`MEDIAMOP_TRUSTED_BROWSER_ORIGINS`** if stricter POST checks) to the real web origin.
- Session cookies typically need **`SameSite=None; Secure`** on the API for credentialed cross-origin `fetch` when not using a dev proxy.

## Troubleshooting (local dev)

1. **`npm` / `npm run dev` fails**  
   Install **Node.js LTS** and open a **new** terminal. From repo root: **`.\scripts\dev-web.ps1`**.

2. **`npm run dev` starts but login/setup is broken**  
   Use the **Vite proxy** (same origin); do not set **`VITE_API_BASE_URL`** unless you intend split-origin dev.

3. **“Cannot reach the API” vs HTTP 503**  
   **`GET /health`** on the API port (**`scripts/dev-ports.json`**) should return **200** when uvicorn is up (process liveness). **`/api/v1`** still needs **`MEDIAMOP_SESSION_SECRET`**, **`alembic upgrade head`**, and a **writable** database path under **`MEDIAMOP_HOME`**. The web shell treats **network errors** (no TCP response) separately from **HTTP 503** from a live API (see **`apps/web`** error guards + **`ApiEntryError`**).

4. **SQLite / migrations**  
   Confirm **`.\scripts\dev-migrate.ps1`** completed without errors. If the DB file lives on a read-only volume, set **`MEDIAMOP_HOME`** (or **`MEDIAMOP_DB_PATH`**) to a writable location.

5. **Python import errors (`No module named mediamop`)**  
   Use **`PYTHONPATH=src`** and cwd **`apps/backend`**, or **`.\scripts\dev-backend.ps1`**.

6. **Port already in use**  
   See **`scripts/dev-ports.json`**. **`MEDIAMOP_DEV_API_PORT`** + **`VITE_DEV_API_PROXY_TARGET`** can override for one session.

7. **Two dev windows**  
   **`.\scripts\dev.ps1`** (launcher only — preflight warns if `.env` / session secret are missing). Full check: **`.\scripts\verify-local.ps1`** with API running.

## Optional `docker-compose.yml` (PostgreSQL)

The repo may still ship a **`docker-compose.yml`** that starts **PostgreSQL** on host port **5433**. **MediaMop’s backend does not use it** in the SQLite-first configuration. Treat it as optional infrastructure for other experiments, not part of the default onboarding path.

## Visual shell

The forward **source of truth** for the product UI is **`apps/web`**.
