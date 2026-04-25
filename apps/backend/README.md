# MediaMop — backend spine

Python package **`mediamop`** lives under `src/mediamop/`. See **`../../docs/adr/`** and the repository **README**.

## HTTP conventions

- **`GET /health`** — root liveness (probe-friendly).
- **`/api/v1`** — versioned JSON product API.

### Auth (Phase 5)

Requires **`MEDIAMOP_SESSION_SECRET`**, a writable SQLite file under **`MEDIAMOP_HOME`** / **`MEDIAMOP_DB_PATH`**, and Alembic at **`0001_initial_auth`** or newer.

| Method | Path | Notes |
|--------|------|--------|
| GET | `/api/v1/auth/csrf` | Issue signed CSRF token for login/logout. |
| POST | `/api/v1/auth/login` | JSON `username`, `password`, `csrf_token`; sets **HttpOnly** session cookie (opaque token). |
| POST | `/api/v1/auth/logout` | **X-CSRF-Token** (or body `csrf_token`); revokes server session; clears cookie. |
| GET | `/api/v1/auth/me` | Current user from cookie + ``UserSession`` row. |
| GET | `/api/v1/auth/bootstrap/status` | Whether first-run bootstrap is allowed (no ``admin`` user yet). |
| POST | `/api/v1/auth/bootstrap` | Create initial ``admin`` only while bootstrap is allowed; CSRF + optional Origin checks (Phase 6). |
| GET | `/api/v1/auth/admin/ping` | Authenticated **admin** probe (uses ``RequireAdminDep``). |

When trusted browser origins are configured — **`MEDIAMOP_TRUSTED_BROWSER_ORIGINS`** if set, otherwise **`MEDIAMOP_CORS_ORIGINS`** — browser **POST** auth routes require a matching **Origin** or **Referer**.

**Phase 6** adds in-process **rate limits** on ``POST .../login`` and ``POST .../bootstrap`` (see env vars below), **security headers** on all responses (CSP baseline; **HSTS** only via ``MEDIAMOP_SECURITY_ENABLE_HSTS`` when always-on HTTPS is true), and a **bounded bootstrap** path (not registration or user admin).

See `mediamop/api/router.py` for composition.

## Configuration

Copy **`.env.example`** to **`.env`** in this directory (gitignored). The API loads **`.env`** on startup; Alembic loads it too. Variables use the **`MEDIAMOP_*`** prefix only.

**`MEDIAMOP_HOME`:** canonical on-disk root for future MediaMop file artifacts (not “this Git clone” as an implicit data directory; see ADR intent in **`../../docs/local-development.md`**). Defaults: Windows `%PROGRAMDATA%\MediaMop`, Unix `XDG_DATA_HOME|mediamop` or `~/.local/share/mediamop`. Exposed as `MediaMopSettings.mediamop_home`.

| Variable | Purpose |
|----------|---------|
| `MEDIAMOP_TRUSTED_BROWSER_ORIGINS` | Optional comma-separated origins for unsafe POST ``Origin``/``Referer`` checks; overrides CORS list for that purpose when set. |
| `MEDIAMOP_AUTH_LOGIN_RATE_MAX_ATTEMPTS` | Max ``POST /auth/login`` attempts per IP per window (default `30`). |
| `MEDIAMOP_AUTH_LOGIN_RATE_WINDOW_SECONDS` | Window length in seconds (default `60`). |
| `MEDIAMOP_BOOTSTRAP_RATE_MAX_ATTEMPTS` | Max ``POST /auth/bootstrap`` per IP per window (default `10`). |
| `MEDIAMOP_BOOTSTRAP_RATE_WINDOW_SECONDS` | Bootstrap window (default `3600`). |
| `MEDIAMOP_SECURITY_ENABLE_HSTS` | If `1`/`true`, send ``Strict-Transport-Security`` on responses. Only when **all** clients use HTTPS. |

## Run API (development)

From this directory, with dependencies installed (`pip install -e ".[dev]"`):

```powershell
$env:PYTHONPATH = "src"
uvicorn mediamop.api.main:app --reload --host 127.0.0.1 --port 8788
```

Health: `GET http://127.0.0.1:8788/health` (see **`../../docs/ports.md`** and **`../../scripts/dev-ports.json`**)

The API always opens SQLite from **`MediaMopSettings.sqlalchemy_database_url`** (derived from **`MEDIAMOP_HOME`** and optional **`MEDIAMOP_DB_PATH`**). **`GET /health`** does not need schema; **`/api/v1/**`** needs **`MEDIAMOP_SESSION_SECRET`**, migrations applied, and a readable/writable DB file.

For the React/Vite app in **`../web`**, local dev uses the **Vite `/api` proxy** to the API port in **`../../scripts/dev-ports.json`** (same-origin cookies on the web port). If you run the SPA against the API origin directly, set `MEDIAMOP_CORS_ORIGINS` (comma-separated), e.g. `http://127.0.0.1:8782`, and see **`../web/README.md`** / **`../../docs/local-development.md`** for split-origin and production cookie notes.

## Alembic

From **`apps/backend`** with **`PYTHONPATH=src`** (same env as the API — **`MEDIAMOP_HOME`** / **`MEDIAMOP_DB_PATH`**):

```powershell
$env:PYTHONPATH = "src"
alembic upgrade head
```

Revision **`0001_initial_auth`** creates **`users`** and **`user_sessions`**. Later revisions add **`activity_events`**.

## Database sessions in routes

Use **`DbSessionDep`** from `mediamop.api.deps`. A **503** here means the app lifespan did not attach a session factory (abnormal); **`GET /health`** does not use the ORM.
