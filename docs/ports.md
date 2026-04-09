# MediaMop — ports (canonical)

**Single source of numeric defaults:** [`scripts/dev-ports.json`](../scripts/dev-ports.json)  
Vite reads it from [`apps/web/vite.config.ts`](../apps/web/vite.config.ts). PowerShell dev scripts read the same file.

## Development (local machine)

| Role | Host | Port | URL example |
|------|------|------|-------------|
| Web shell (Vite **dev** and **preview**) | `127.0.0.1` | **8782** | `http://127.0.0.1:8782` |
| API (uvicorn per `scripts/dev-backend.ps1`) | `127.0.0.1` | **8788** | `http://127.0.0.1:8788` |

The browser should use the **web** URL. `/api` is proxied to the API origin above (same-origin cookies).

**Overrides (temporary):**

- API port: `MEDIAMOP_DEV_API_PORT` when running `dev-backend.ps1`.
- Vite proxy target: `VITE_DEV_API_PROXY_TARGET` (must match wherever uvicorn listens).

**Changing defaults:** edit `scripts/dev-ports.json` and restart dev servers.

## Production

There is **no fixed “production port” in application code**. Deployments use normal HTTPS:

- **Clients** talk to **`https://<your-domain>` on port 443** (standard TLS).
- The API is usually **the same origin** (`https://<your-domain>/api/...` behind a reverse proxy) or a **separate hostname**, still on **443**.

For **containers** (Docker/Kubernetes), the API process bind port (e.g. **8000** inside the container) is an implementation detail. `dev-ports.json` includes **`production.containerApiBindPort`** as a documented convention for examples only—set the real port in your orchestration layer and reverse proxy.

## Other local services

| Service | Default host port | Notes |
|---------|-------------------|--------|
| PostgreSQL (**native** install, typical) | **5432** | First-class on Windows; not related to web/API ports above |
| PostgreSQL (**optional** `docker-compose.yml` in this repo) | **5433** → container **5432** | Developer convenience only; not a Windows prerequisite |

## CI / E2E

Automated tests pick **ephemeral loopback ports** (see `tests/e2e/mediamop/conftest.py`) so they do not depend on 8782/8788 being free.
