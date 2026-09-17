---
sidebar_position: 1
title: Docker
---

# Docker Deployment

Weir ships as an all-in-one container: the .NET server, SQLite and the bundled web UI on port 8788.

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

No `.env` file is required for the default path. The container generates its own session secret if you don't provide one and keeps it at `$WEIR_HOME/session.secret`, so it survives restarts.

## What's in the image

- Images are published for **linux/amd64** and **linux/arm64** (`ghcr.io/jampat000/weir:latest` and `:X.Y.Z`)
- A self-contained .NET server at `/opt/weir/Weir`, with the web UI at `/opt/weir/web-dist`
- ffmpeg, curl and gosu on a slim Debian base (`mcr.microsoft.com/dotnet/runtime-deps:10.0-bookworm-slim`)
- Runs as the `weir` user (UID/GID 1000 by default)
- Data volume `/data/weir`, port `8788`
- A built-in health check on `/health`

## Architecture

- One container, one process, one SQLite database
- Same-origin API under `/api/v1`
- Stable tags published by the release workflow
- The server creates or updates its database itself on start; there is no migration command to run

## Volume and persistence

Persist `WEIR_HOME` on a durable volume so SQLite data survives container replacement:

```yaml
volumes:
  - weir-data:/data/weir
```

Keep `WEIR_SESSION_SECRET` stable across upgrades so browser sessions remain valid.

## NAS and permissions

If the container needs to write as a specific NAS or host user, set:

- `WEIR_PUID` / `WEIR_PGID` — the entrypoint remaps the `weir` user to this UID/GID before starting the server

The `WEIR_CHOWN_*` and `WEIR_DIR_MODE_*` settings are still checked for valid values but are **not applied**. They had already stopped taking effect when folders moved onto libraries (#363). Set ownership and permissions on your host folders directly, or pick a `WEIR_PUID` / `WEIR_PGID` that can already write to them.

## What not to do

- **Do not** run more than one Weir server process against the same database
- **Do not** run multiple containers against the same SQLite database
- **Do not** use `WEIR_CORS_ORIGINS=*` (rejected at startup)

## Upgrade continuity

| Setting | Why it matters |
|---------|---------------|
| `WEIR_HOME` volume | SQLite data survives container replacement |
| `WEIR_SESSION_SECRET` | Browser sessions remain valid across upgrades |
