---
sidebar_position: 1
title: Quickstart
---

# Quickstart

Get Weir running locally in under five minutes.

## Prerequisites

- **Python 3.11+**
- **Node.js LTS** (npm on `PATH`)

## 1. Clone and set up the backend

```powershell
git clone https://github.com/jampat000/weir.git
cd Weir/apps/backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements-runtime.lock
python -m pip install --no-deps --no-build-isolation -e .
```

## 2. Configure environment

Copy `apps/backend/.env.example` to `apps/backend/.env` and set:

- **`WEIR_SESSION_SECRET`** — a long random string (required for auth)
- **`WEIR_CREDENTIALS_SECRET`** — a separate long random value (required before saving provider credentials)

## 3. Run database migrations

From the repository root:

```powershell
.\scripts\dev-migrate.ps1
```

## 4. Start the dev stack

```powershell
cd apps/web
npm ci
npm run dev
```

Open **http://localhost:8782/** in your browser. You'll be guided through first-run setup.

## What's running

| Component | URL | Port |
|-----------|-----|------|
| Web UI (Vite dev server) | http://localhost:8782 | 8782 |
| API (uvicorn) | http://127.0.0.1:8788 | 8788 |

The Vite dev server proxies `/api` requests to the backend automatically — no CORS configuration needed for local development.

## Next steps

- [Docker deployment](deployment/docker) — run Weir in a container
- [Windows installer](deployment/windows) — install as a desktop app
- [Architecture overview](architecture/overview) — understand how Weir is structured
