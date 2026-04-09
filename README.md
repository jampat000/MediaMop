# MediaMop

<!-- README_LOCKED_SECTION_START: project-note -->
## A note on this project

This is a vibe coded project. I don't know how to code and I have nothing but respect for the people who do.

I needed something that fit my exact requirements and couldn't find anything out in the wild that did what I wanted, so I built it — with a lot of help from AI.

Every feature exists because I needed it.
Every decision was made because it made sense to me as a user first.

If it's useful to you, feel free to use it.
I'm not forcing it on anyone and I'm not hiding behind anything.

Take it, fork it, do whatever you want with it.

— Built by someone who just wanted their media library to work properly.

<!-- README_LOCKED_SECTION_END: project-note -->

MediaMop is a standalone product: **FastAPI + PostgreSQL** backend (`apps/backend`) and **React + Vite** web shell (`apps/web`). This repository is **not** the Fetcher app; Fetcher remains a separate codebase.

## Quick start

**Prerequisites:** **Python 3.11+**, **Node.js LTS** (npm on `PATH`), **PostgreSQL 16+**. On Windows, install PostgreSQL with the official installer (or use an existing instance); **Docker is not required**. Open a **new** PowerShell window after installing Node so `npm` resolves.

**PostgreSQL** is a core dependency. **Windows-native** installs are first-class: create a database and user, point **`MEDIAMOP_DATABASE_URL`** at it (often **`127.0.0.1:5432`**). **Optional:** this repo includes **`docker-compose.yml`** to run Postgres on host port **5433** for developer convenience—it is **not** a product prerequisite on Windows.

From the **repository root**, in order:

1. **PostgreSQL** — Ensure the server is running and a database exists. See **[`docs/local-development.md`](docs/local-development.md)** for the **Windows native** path and the **optional Docker** path.
2. **Backend Python env (one-time)** — `cd apps/backend` → `py -3 -m venv .venv` → `.\.venv\Scripts\Activate.ps1` → `pip install -e .`
3. **Backend `.env` (one-time)** — `copy .env.example .env` in `apps/backend`, then set **`MEDIAMOP_DATABASE_URL`** and **`MEDIAMOP_SESSION_SECRET`**. The API and Alembic **load `apps/backend/.env` automatically**; shell env vars still override.
4. **Migrations** — From repo root: **`.\scripts\dev-migrate.ps1`**, or manually `alembic upgrade head` from `apps/backend` with **`PYTHONPATH=src`**. The script loads **`apps/backend/.env`** into the process (shell env overrides). **`MEDIAMOP_DATABASE_URL` must be set** (uncommented in **`.env`** or in the shell). Optional Docker Compose Postgres on **`127.0.0.1:5433`** is **opt-in only**: **`.\scripts\dev-migrate.ps1 -UseComposeDevDb`**.
5. **API** — From repo root: **`.\scripts\dev-backend.ps1`**. Confirm **`GET /health`** on the API port (**`scripts/dev-ports.json`**) returns **200** — that is **liveness only**. JSON under **`/api/v1`** stays **503** until **`MEDIAMOP_DATABASE_URL`**, **`MEDIAMOP_SESSION_SECRET`**, and **Alembic head** are in place.
6. **Web** — Second terminal: **`.\scripts\dev-web.ps1`**. Open **`http://127.0.0.1:8782`**. Leave **`VITE_API_BASE_URL`** unset for the Vite **`/api`** proxy.

**Optional:** **`.\scripts\dev.ps1`** opens API + web in two windows (launcher only; run PostgreSQL + `.env` + **`.\scripts\dev-migrate.ps1`** first). **`.\scripts\verify-local.ps1`** runs unit tests, then (unless **`-SkipLiveChecks`**) checks env, DB + Alembic head, live **`/health`** and **`/api/v1/auth/bootstrap/status`**, and **static** Vite proxy lines in **`vite.config.ts`** (not a live browser/proxy proof).

Canonical ports: **[`docs/ports.md`](docs/ports.md)**.

Full instructions: **[`docs/local-development.md`](docs/local-development.md)**.

## Product paths

Runtime file layout is anchored by **`MEDIAMOP_HOME`** (optional). Defaults are OS-appropriate (`%LOCALAPPDATA%\MediaMop` on Windows, XDG data dir on Linux/macOS). It must **not** default to “whatever Git clone directory you’re in.” Details in [`docs/local-development.md`](docs/local-development.md).

## Architecture

Locked decisions live under [`docs/adr/`](docs/adr/).

## Transitional Jinja app

An older Jinja/SQLite experiment lived in another repository; it is **not** part of this tree and is **not** the active shell. **`apps/web`** is the visual source of truth for the product UI.
