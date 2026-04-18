# MediaMop — web shell

**React + TypeScript + Vite** app: real consumer of `apps/backend` cookie session auth and bootstrap APIs. **This directory is the forward visual source of truth** for the MediaMop shell (tokens, logo, **Outfit**, sidebar/main). Branding was initially ported from an older static/CSS spike (not maintained in this repository); ongoing UI work should live here only.

**Version:** the shell footer reads **`package.json`** `version`, injected at build time via `vite.config.ts` `define` (`WEB_APP_VERSION` in `src/lib/app-meta.ts`).

## Stack

- React 18, React Router 6, TanStack Query
- Tailwind CSS (minimal tokens in `tailwind.config.js`); **shell look** is owned by `src/styles/mediamop-tokens.css` and `src/styles/mediamop-shell.css` - **warm charcoal base + gold accent** product language (approved one-pager direction); indigo only as a restrained depth veil in tokens.
- Vitest + Testing Library for small unit tests

## Development

```powershell
cd apps/web
npm ci
npm run dev
```

**`npm run dev`** starts **both** the FastAPI process (same as `../../scripts/dev-backend.ps1`) and Vite in one terminal, so the `/api` proxy always has a backend. Use **`npm run dev:web`** for Vite only (e.g. when the API is already running elsewhere).

**`package-lock.json`** is committed; use **`npm ci`** for reproducible installs (CI uses **`npm ci`**).

- **Frontend:** **`http://127.0.0.1:8782`** (locked in **`../../scripts/dev-ports.json`**; see **`../../docs/ports.md`**)
- **Backend (standalone):** **`../../scripts/dev-backend.ps1`** or uvicorn on the **API** host/port from the same JSON file.

Vite **`server`** and **`preview`** proxy **`/api`** to that API origin (override with `VITE_DEV_API_PROXY_TARGET`). The browser uses one origin for the page and `/api/*`, so **HttpOnly** cookies work in dev and **`npm run preview`** (E2E uses ephemeral ports).

Do not point the SPA at the raw API port unless CORS and cookie **`SameSite`** / **`Secure`** are set for cross-origin deployment.

### Backend CORS / trusted origins

For **non-proxied** setups (e.g. static hosting on another port), set on the backend:

- `MEDIAMOP_CORS_ORIGINS` — include the exact web origin (e.g. `http://127.0.0.1:8782`)
- Optionally `MEDIAMOP_TRUSTED_BROWSER_ORIGINS` for stricter POST Origin/Referer checks

Then set in this app:

- `VITE_API_BASE_URL` — split-origin dev/production API origin (no trailing slash); not needed when using the Vite `/api` proxy

**Production (split origins):** use **HTTPS** end-to-end; set **`MEDIAMOP_CORS_ORIGINS`** / **`MEDIAMOP_TRUSTED_BROWSER_ORIGINS`** to the real web origin; set **`VITE_API_BASE_URL`** here to the API origin (no trailing slash). Session cookies on the API host generally need **`SameSite=None; Secure`** so credentialed `fetch` from the web origin works. The backend’s cookie flags are env-driven — see ADR-0003 and **`../../docs/local-development.md`**.

## Routes

| Path | Purpose |
|------|---------|
| `/` | Resolves to `/app`, `/setup`, or `/login` from `/me` + bootstrap status |
| `/setup` | First-run admin creation (`POST /api/v1/auth/bootstrap`) while allowed; otherwise redirects |
| `/login` | Session login (`POST /api/v1/auth/login`) |
| `/app` | Dashboard placeholder (authenticated shell) |
| `/app/settings` | Suite settings: Global (saved in-app) and Security (read-only startup snapshot) |

## API usage

All calls use `credentials: 'include'` and the real endpoints:

- `GET /api/v1/auth/bootstrap/status`
- `GET /api/v1/auth/csrf`
- `POST /api/v1/auth/bootstrap`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`

**No** `localStorage` (or other browser storage) for session or tokens — TanStack Query caches in memory only.

## Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Vite dev server + API proxy |
| `npm run build` | Typecheck + production bundle |
| `npm run preview` | Preview production build |
| `npm run test` | Vitest |
| `npm run ci` | `build` + `test` (matches CI gate for this package) |

## CI

GitHub Actions **Test** workflow runs **`npm ci`**, **`npm run build`**, and **`npm run test`** in this directory after backend tests, then Playwright E2E in `tests/e2e/mediamop/` against a real API + **`vite preview`** (see **`../../docs/local-development.md`**).

## Intentionally not built

- Module pages (Fetcher, refiner, pruner, settings product, …)
- Role-based navigation / permissions UI
- Non-session auth (JWT-in-browser, token storage)

See **`../../docs/adr/`** (especially ADR-0003).
