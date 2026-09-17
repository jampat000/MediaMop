---
sidebar_position: 1
title: Quickstart
---

# Quickstart

Get Weir running locally in under five minutes.

## Prerequisites

- **.NET 10 SDK** (`dotnet` on `PATH`; the exact version is pinned in `apps/server/global.json`)
- **Node.js 24** (npm on `PATH`)

Python is not needed to run Weir.

## 1. Clone the repository

```powershell
git clone https://github.com/jampat000/Weir.git
cd Weir
```

## 2. Configure environment

Copy `.env.example` to `.env` in the repository root and set:

- **`WEIR_SESSION_SECRET`** — a long random string (required for auth)
- **`WEIR_CREDENTIALS_SECRET`** — a separate long random value (required before saving provider credentials)

## 3. Start the dev stack

```powershell
cd apps/web
npm ci
npm run dev
```

This starts the .NET server (with `dotnet watch`) and the Vite dev server together. If you prefer two terminals, run `.\scripts\dev-backend.ps1` in one and `.\scripts\dev-web.ps1` in the other.

There is no separate migration step. The server creates its SQLite database, or brings an existing one up to date, when it starts.

Open **http://localhost:8782/** in your browser. You'll be guided through first-run setup.

## What's running

| Component | URL | Port |
|-----------|-----|------|
| Web UI (Vite dev server) | http://localhost:8782 | 8782 |
| API (the .NET server) | http://127.0.0.1:8788 | 8788 |

The Vite dev server proxies `/api` requests to the server automatically — no CORS configuration needed for local development.

## Next steps

- [Docker deployment](deployment/docker) — run Weir in a container
- [Windows installer](deployment/windows) — install as a desktop app
- [Architecture overview](architecture/overview) — understand how Weir is structured
