# MediaMop — local development (backend + web)

This **MediaMop** repository contains **`apps/backend`** (FastAPI, PostgreSQL, cookie sessions) and **`apps/web`** (React/Vite). It does **not** include the Fetcher app or Fetcher’s Docker stack.

**Local web/API ports** are versioned in **`scripts/dev-ports.json`**; the policy is summarized in **[`docs/ports.md`](ports.md)**.

## Windows — native PostgreSQL (first-class)

On Windows, **install and run PostgreSQL without Docker** (e.g. **EDB PostgreSQL** installer or **winget**). Create a database and role, then set:

- **`MEDIAMOP_DATABASE_URL`** — e.g. `postgresql+psycopg://YOUR_USER:YOUR_PASSWORD@127.0.0.1:5432/YOUR_DB` (**5432** is the default listen port for a typical local install).

Copy **`apps/backend/.env.example`** → **`apps/backend/.env`** and put the URL and **`MEDIAMOP_SESSION_SECRET`** there (see below). Run migrations (**`.\scripts\dev-migrate.ps1`** with the URL set, or **`alembic upgrade head`** from **`apps/backend`** with **`PYTHONPATH=src`**).

**Docker is not required** on Windows for normal development.

## Optional — PostgreSQL via Docker Compose (developer convenience)

If you **choose** to use Docker for Postgres only: from the repo root run **`docker compose up -d`**. The bundled file maps host **`5433`** → container **5432** to avoid clashing with a native Postgres on **5432**.

Example URL for that optional stack:

`postgresql+psycopg://mediamop:mediamop@127.0.0.1:5433/mediamop`

Do **not** treat this as the only supported path; it is optional on Windows.

## Linux — development and container deployment

On Linux, PostgreSQL may be a **system package**, **managed service**, or **Docker/Compose** stack. Set **`MEDIAMOP_DATABASE_URL`** accordingly. The same **`docker-compose.yml`** remains a valid way to run Postgres for local dev or small deployments when you want containers.

**CI** uses a **`postgres:16`** **service** in **`.github/workflows/ci.yml`** (Linux runner) — that is CI infrastructure, not a statement that developers must use Docker locally.

## Backend `.env` (local)

Copy **`apps/backend/.env.example`** to **`apps/backend/.env`** and set **`MEDIAMOP_DATABASE_URL`** and **`MEDIAMOP_SESSION_SECRET`**. The running API loads this file automatically (see **`MediaMopSettings.load`**), and **Alembic** loads it too. Shell variables still override if both are set.

**Migrations from repo root:** **`.\scripts\dev-migrate.ps1`** — it loads **`apps/backend/.env`** into the process (shell variables still win). **`MEDIAMOP_DATABASE_URL` must be set** (uncommented in **`.env`** or in the shell). There is **no silent default** to Compose. To migrate against optional Compose Postgres on **`127.0.0.1:5433`**, run **`.\scripts\dev-migrate.ps1 -UseComposeDevDb`** (after **`docker compose up -d`**).

## MediaMop home (product paths)

On-disk runtime defaults must **not** be tied to “the Git clone directory” or the process current working directory.

- **`MEDIAMOP_HOME`** (optional): explicit absolute root for product-owned data. Loaded into `MediaMopSettings.mediamop_home`.
- **Default when unset:**
  - **Windows:** `%LOCALAPPDATA%\MediaMop`
  - **Linux/macOS:** `$XDG_DATA_HOME/mediamop`, or `~/.local/share/mediamop`

The backend does **not** yet write logs or cache under this root automatically; it is the **canonical** anchor for future artifacts (see `apps/backend/src/mediamop/core/paths.py`). PostgreSQL URLs remain **separate** (`MEDIAMOP_DATABASE_URL`).

**Linux containers:** set `MEDIAMOP_HOME` to a volume mount (e.g. `/var/lib/mediamop`) so data survives restarts.

## Apply migrations

From repo root (**`.\scripts\dev-migrate.ps1`**) or manually:

```powershell
cd apps/backend
$env:PYTHONPATH = "src"
# Native Postgres example (adjust user, password, db):
$env:MEDIAMOP_DATABASE_URL = "postgresql+psycopg://mediamop:secret@127.0.0.1:5432/mediamop"
alembic upgrade head
```

Optional Compose example (host port **5433** only if you started **`docker compose up -d`**):

```text
postgresql+psycopg://mediamop:mediamop@127.0.0.1:5433/mediamop
```

## Backend API

```powershell
cd apps/backend
$env:PYTHONPATH = "src"
$env:MEDIAMOP_DATABASE_URL = "postgresql+psycopg://..."
$env:MEDIAMOP_SESSION_SECRET = "<long random>"
# $env:MEDIAMOP_CORS_ORIGINS = "http://127.0.0.1:8782"
uvicorn mediamop.api.main:app --host 127.0.0.1 --port 8788 --reload
```

## Web app

```powershell
cd apps/web
npm ci
npm run dev
```

The Vite dev server and **`vite preview`** use **[`scripts/dev-ports.json`](../scripts/dev-ports.json)**. See **[`docs/ports.md`](ports.md)**. To override temporarily, set **`VITE_DEV_API_PROXY_TARGET`** and **`MEDIAMOP_DEV_API_PORT`** together.

## CI validation

The **`Test`** workflow:

1. Runs **`apps/backend`** tests against a **Linux** Postgres **service** + Alembic.
2. Runs **`npm ci` → `npm run build` → `npm run test`** in **`apps/web`**.
3. Runs **E2E** with **`MEDIAMOP_E2E=1`**, uvicorn + **`vite preview`** + Playwright.

## E2E (local, optional)

Requires: Postgres, Playwright + Chromium, Node/npm, built web shell.

```powershell
cd apps/web
npm ci
npm run build
cd ../..
$env:MEDIAMOP_E2E = "1"
$env:MEDIAMOP_DATABASE_URL = "postgresql+psycopg://..."
$env:MEDIAMOP_SESSION_SECRET = "local-dev-secret-at-least-32-characters-long"
pytest tests/e2e/mediamop -q --tb=short
```

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
   **`GET /health`** on the API port (**`scripts/dev-ports.json`**) should return **200** when uvicorn is up (process liveness). That does **not** mean **`/api/v1`** is ready: without DB URL, secret, and migrations, auth JSON routes return **503**. The web shell treats **network errors** (no TCP response) separately from **HTTP 503** from a live API (see **`apps/web`** error guards + **`ApiEntryError`**).

4. **PostgreSQL**  
   **Windows:** Prefer **native** install (**`127.0.0.1:5432`** typical). **Optional:** **`docker compose up -d`** exposes **5433** on the host (see `docker-compose.yml`). Set **`MEDIAMOP_DATABASE_URL`** to match whichever you use.

5. **Python import errors (`No module named mediamop`)**  
   Use **`PYTHONPATH=src`** and cwd **`apps/backend`**, or **`.\scripts\dev-backend.ps1`**.

6. **Port already in use**  
   See **`scripts/dev-ports.json`**. **`MEDIAMOP_DEV_API_PORT`** + **`VITE_DEV_API_PROXY_TARGET`** can override for one session.

7. **Two dev windows**  
   **`.\scripts\dev.ps1`** (launcher only — preflight warns if `.env` / DB URL / session secret are missing). Full check: **`.\scripts\verify-local.ps1`** with API running.

## Visual shell

The forward **source of truth** for the product UI is **`apps/web`**.
