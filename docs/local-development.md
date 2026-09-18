# Weir — local development (server + web)

This **Weir** repository contains **`apps/server`** (the C# / .NET 10 server: HTTP API, **SQLite**, cookie sessions, the job queue and Processing), **`apps/web`** (React/Vite) and **`apps/tray`** (the Windows tray app). Media manager connections (Radarr, Sonarr, Deluno, or anything posting Weir's own payload) live under **Settings -> Media managers**; inbound events all arrive at `POST /api/v1/intake/webhook/{source}`. Library automation and failed-import tooling ship as part of the **Processing** surface, not as separate dashboard apps. See [ADR-0013](adr/ADR-0013-media-managers-are-kinds-not-products.md).

**Local web/API ports** are versioned in **`scripts/dev-ports.json`**; the policy is summarized in **[`docs/ports.md`](ports.md)**.

## Prerequisites

- **.NET 10 SDK** (pinned in **`apps/server/global.json`**)
- **Node.js 24** (npm on `PATH`)
- **Python 3.11+** only for the contract suite and E2E test runners (they judge the server from outside; nothing in Weir runs on Python)

## One-time setup (after cloning)

Activate the pre-push hook so the contract suite lint, prettier, the dead-code guard and the OpenAPI types drift check run locally before every push:

```powershell
git config core.hooksPath .githooks
```

The hook delegates to `scripts/pre-push-check.ps1`. It skips checks gracefully if `ruff` or `apps/web/node_modules` are not yet installed — set those up first for full coverage.

The server persists state in **file-backed SQLite** under **`WEIR_HOME`** and creates or migrates its database itself when it starts; there is no separate migration command. You do **not** install or run PostgreSQL for normal Weir development.
Docker Desktop is not required for normal local development or for shipping a release.

## `.env` (local)

Copy **`.env.example`** → **`.env`** at the repository root.

Required for auth and `/api/v1`:

- **`WEIR_SESSION_SECRET`** — long random value.

Optional path overrides (defaults are under the OS-specific **`WEIR_HOME`**):

- **`WEIR_HOME`**, **`WEIR_DB_PATH`**, **`WEIR_BACKUP_DIR`**, **`WEIR_LOG_DIR`**, **`WEIR_TEMP_DIR`**

The server itself reads **`WEIR_*`** from its environment only. The dev launchers (**`scripts/dev-backend.ps1`**, **`scripts/dev.ps1`**, **`npm run dev`**) load **`.env`** into that environment first; shell variables still override.

## Server (`apps/server`)

Build and test from the repo root ([ADR-0017](adr/ADR-0017-backend-on-dotnet.md); more in **[`apps/server/README.md`](../apps/server/README.md)**):

```powershell
dotnet build apps/server/Weir.slnx -warnaserror
dotnet test apps/server/Weir.slnx
```

Run it:

```powershell
.\scripts\dev-backend.ps1
```

That loads **`.env`**, defaults **`WEIR_HOME`** to **`.local-dev-home`** in the repository, serves **`apps/web/dist`** when it has been built, and runs **`dotnet watch run`** on **`apps/server/src/Weir.Host`** bound to the API host and port in **`scripts/dev-ports.json`**. By hand:

```powershell
$env:WEIR_SESSION_SECRET = "<long random>"
$env:WEIR_HOME = "$PWD\.local-dev-home"
# $env:WEIR_CORS_ORIGINS = "http://127.0.0.1:8782"
dotnet run --project apps/server/src/Weir.Host -- --host 127.0.0.1 --port 8788
```

Forgot the local admin password? **`.\scripts\dev-reset-auth.ps1 --list`** shows the accounts and **`--yes`** clears users and sessions so **`/setup`** works again.

## Web app

```powershell
cd apps/web
npm ci
npm run dev
```

**`npm run dev`** clears processes listening on the **default** dev API and web ports from **`scripts/dev-ports.json`**, then starts the .NET server (**`dotnet watch run`**) and Vite together (see **`apps/web/scripts/run-dev-stack.mjs`**). Use **`npm run dev:quick`** only when you are sure those ports are already free.

The Vite dev server and **`vite preview`** use **[`scripts/dev-ports.json`](../scripts/dev-ports.json)**. See **[`docs/ports.md`](ports.md)**. To override temporarily, set **`VITE_DEV_API_PROXY_TARGET`** and **`WEIR_DEV_API_PORT`** together.

### API contract and generated types (OpenAPI)

**`apps/web/openapi/weir-openapi.json`** is the committed API contract. The server embeds it at build time and serves it at **`/openapi.json`** (pruned to the operations it maps, with its own version), and the web app's TypeScript types are generated from it:

```powershell
cd apps/web
npm run api:types:generate   # regenerate src/lib/api/generated/openapi-types.ts
npm run api:types:check      # CI: fails when the generated types are stale
```

When you add or change an endpoint, edit **`weir-openapi.json`** in the same change (it used to be exported from the Python backend; it is maintained by hand now), regenerate the types, and keep **`OpenApiDocumentParityTests`** in **`apps/server/tests/Weir.Api.Tests`** passing.

## Weir home (product paths)

On-disk runtime defaults must **not** be tied to “the Git clone directory” or the process current working directory.

- **`WEIR_HOME`** (optional): explicit absolute root for product-owned data.
- **Default when unset:**
  - **Windows:** `%PROGRAMDATA%\Weir` (normally `C:\ProgramData\Weir`)
  - **Linux/macOS:** `$XDG_DATA_HOME/weir`, or `~/.local/share/weir`

The default SQLite file is **`{WEIR_HOME}/data/weir.sqlite3`** unless **`WEIR_DB_PATH`** overrides.

**Linux containers:** set `WEIR_HOME` to a volume mount (e.g. `/var/lib/weir`) so data survives restarts.

## CI validation

The **`Test`** workflow (`.github/workflows/ci.yml`), path-aware:

1. **`weir`** (required): **`dotnet build -warnaserror`**, **`dotnet test`** and a NuGet vulnerability scan for **`apps/server`**; **`npm ci`**, **`api:types:check`**, lint, format, build and unit tests in **`apps/web`**; the dead-code guard; then **E2E** with **`WEIR_E2E=1`**, **`WEIR_HOME`** on a temp dir, the .NET server serving the built web app (**`WEIR_WEB_DIST`**, as the packages do) + Playwright (from repo-root **`tests/e2e/weir/`**, same as local optional E2E below).
2. **`weir-server (windows-latest)`**: the server build and tests on Windows.
3. **`contract (dotnet)`**: the contract suite against the .NET server, every area required.
4. **`docker-smoke`** (required): builds the image, runs it and the live packaged audit; builds the linux/arm64 image too when the Docker files change.
5. **`windows-package-smoke`** (required): tray tests, the Velopack build and **`scripts/smoke-windows-package.ps1`**.

Pushing a semver tag **`v*`** runs the **`Release`** workflow, which repeats these stages before publishing a GitHub Release — see **[`docs/release.md`](release.md)**.

## Contract suite and E2E (local)

Both are Python test runners. Install their locked dependencies once:

```powershell
python -m pip install --require-hashes -r tests/requirements.txt
python -m playwright install chromium
```

Build the server and the web shell, then run either:

```powershell
dotnet build apps/server/Weir.slnx
cd apps/web
npm ci
npm run build
cd ../..
python -m pytest tests/contract -q --contract-required-only
$env:WEIR_E2E = "1"
$env:WEIR_SESSION_SECRET = "local-dev-secret-at-least-32-characters-long"
python -m pytest tests/e2e/weir -q --tb=short
```

The contract suite is described in **[`tests/contract/README.md`](../tests/contract/README.md)**. For E2E, **`WEIR_E2E_HOME`** gives a fixed data directory (otherwise a temp directory is used), **`WEIR_E2E_SERVER_EXE`** runs a published server instead of **`dotnet run --no-build`**, and **`WEIR_E2E_LEDGER`** overrides the leftover-server ledger (see **`tests/e2e/weir/conftest.py`**).

## Split-origin production (deferred wiring)

If the static site and API are on **different origins**:

- Use **HTTPS** everywhere.
- Set **`WEIR_CORS_ORIGINS`** (and **`WEIR_TRUSTED_BROWSER_ORIGINS`** if stricter POST checks) to the real web origin.
- Session cookies typically need **`SameSite=None; Secure`** on the API for credentialed cross-origin `fetch` when not using a dev proxy.

## Troubleshooting (local dev)

1. **`npm` / `npm run dev` fails**  
   Install **Node.js 24** and open a **new** terminal. From repo root: **`.\scripts\dev-web.ps1`**.

2. **`dotnet` not found, or the API exits during startup**  
   Install the **.NET 10 SDK** and open a new terminal. A build error, a missing **`WEIR_SESSION_SECRET`** or an unwritable **`WEIR_HOME`** stops the server; the reason is in the same terminal.

3. **`npm run dev` starts but login/setup is broken**  
   Use the **Vite proxy** (same origin); do not set **`VITE_API_BASE_URL`** unless you intend split-origin dev.

4. **“Cannot reach the API” vs HTTP 503**  
   **`GET /health`** on the API port (**`scripts/dev-ports.json`**) returns **200** once the server process is up, and **`GET /ready`** reports **`ready: true`** once its database is open. **`/api/v1`** still needs **`WEIR_SESSION_SECRET`** and a **writable** database path under **`WEIR_HOME`**. The web shell treats **network errors** (no TCP response) separately from **HTTP 503** from a live API (see **`apps/web`** error guards + **`ApiEntryError`**).

5. **"Weir cannot start: ... schema"**  
   The server opens a database at its own schema head (or the last schema the retired Python backend wrote) and refuses anything else rather than guess. Point **`WEIR_HOME`** (or **`WEIR_DB_PATH`**) at a fresh folder for a clean database.

6. **Port already in use**  
   See **`scripts/dev-ports.json`**. **`WEIR_DEV_API_PORT`** + **`VITE_DEV_API_PROXY_TARGET`** can override for one session.

7. **Two dev windows**  
   **`.\scripts\dev.ps1`** (launcher only — preflight warns if `.env`, the session secret or `dotnet` are missing). Full check: **`.\scripts\verify-local.ps1`** with the API running.

## Optional Postgres container (developers only)

**Not used by Weir** in normal Docker or SQLite setups — the app stores data in **SQLite** under **`WEIR_HOME`**.

Weir local development is SQLite-first. There is no separate Postgres compose path in the greenfield repo state.

## All-in-one Docker

For a **single-container** runtime (the .NET server + production web UI + ffmpeg, SQLite volume), see **`docker/README.md`** and root **`compose.yaml`**. Build locally with `docker build -t weir:local .`.

For maintainers without working local Docker, use GitHub-hosted validation:

```powershell
.\scripts\verify-docker-remote.ps1
```

The release workflow also builds, publishes, verifies, and smoke-tests Docker on GitHub-hosted runners.

## Visual shell

The forward **source of truth** for the product UI is **`apps/web`**.
