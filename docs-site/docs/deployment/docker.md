---
sidebar_position: 1
title: Docker
---

# Docker Deployment

MediaMop ships as an all-in-one container: FastAPI + SQLite + bundled web UI on port 8788.

## Quick start

```bash
docker pull ghcr.io/jampat000/mediamop:latest
docker run --rm -p 8788:8788 -v mediamop-data:/data/mediamop ghcr.io/jampat000/mediamop:latest
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

Persist `MEDIAMOP_HOME` on a durable volume so SQLite data survives container replacement:

```yaml
volumes:
  - mediamop-data:/data/mediamop
```

Keep `MEDIAMOP_SESSION_SECRET` stable across upgrades so browser sessions remain valid.

## NAS and permissions

If the container needs to write as a specific NAS or host user, set:

- `MEDIAMOP_PUID` / `MEDIAMOP_PGID` — run as a specific UID/GID
- `MEDIAMOP_CHOWN_*` flags — for Refiner watched/work/output folders

## What not to do

- **Do not** add `--workers` to the Docker command
- **Do not** run multiple containers against the same SQLite database
- **Do not** use `MEDIAMOP_CORS_ORIGINS=*` (rejected at startup)

## Upgrade continuity

| Setting | Why it matters |
|---------|---------------|
| `MEDIAMOP_HOME` volume | SQLite data survives container replacement |
| `MEDIAMOP_SESSION_SECRET` | Browser sessions remain valid across upgrades |
