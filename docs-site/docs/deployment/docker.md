---
sidebar_position: 1
title: Docker
---

# Docker Deployment

Weir ships as an all-in-one container: FastAPI + SQLite + bundled web UI on port 8788.

## Quick start

```bash
docker pull ghcr.io/jampat000/weir:latest
docker run --rm -p 8788:8788 -v weir-data:/data/weir ghcr.io/jampat000/weir:latest
```

Or with Docker Compose from a repo clone:

```bash
docker compose pull
docker compose up -d
```

No `.env` file is required for the default path. The container generates and persists its own session secret if you don't provide one.

## Architecture

- One container, one process, one SQLite database
- Same-origin API under `/api/v1`
- Stable tags published by the release workflow

## Volume and persistence

Persist `WEIR_HOME` on a durable volume so SQLite data survives container replacement:

```yaml
volumes:
  - weir-data:/data/weir
```

Keep `WEIR_SESSION_SECRET` stable across upgrades so browser sessions remain valid.

## NAS and permissions

If the container needs to write as a specific NAS or host user, set:

- `WEIR_PUID` / `WEIR_PGID` — run as a specific UID/GID
- `WEIR_CHOWN_*` flags — for Refiner watched/work/output folders

## What not to do

- **Do not** add `--workers` to the Docker command
- **Do not** run multiple containers against the same SQLite database
- **Do not** use `WEIR_CORS_ORIGINS=*` (rejected at startup)

## Upgrade continuity

| Setting | Why it matters |
|---------|---------------|
| `WEIR_HOME` volume | SQLite data survives container replacement |
| `WEIR_SESSION_SECRET` | Browser sessions remain valid across upgrades |
