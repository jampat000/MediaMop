# MediaMop Docker

MediaMop publishes an all-in-one container image with:

- FastAPI backend
- bundled production web UI
- SQLite runtime under `MEDIAMOP_HOME`

The stable image tags are published by the release workflow:

- `ghcr.io/jampat000/mediamop:latest`
- `ghcr.io/jampat000/mediamop:vX.Y.Z`

## Quick start

```bash
docker pull ghcr.io/jampat000/mediamop:latest
docker run --rm \
  -p 8788:8788 \
  -v mediamop-data:/data/mediamop \
  ghcr.io/jampat000/mediamop:latest
```

Open `http://localhost:8788/`.

## Compose

From the repository root:

1. Start MediaMop:

   ```bash
   docker compose pull
   docker compose up -d
   ```

2. Open `http://localhost:8788/`.

If you want to override defaults later, copy `docker/mediamop.env.example` to `.env.mediamop`
and run `docker compose --env-file .env.mediamop up -d`.

## Data and runtime settings

- `MEDIAMOP_HOME` defaults to `/data/mediamop`
- mount a volume if you want SQLite data and runtime files to persist
- if `MEDIAMOP_SESSION_SECRET` is not provided, the container generates one automatically and persists it to `$MEDIAMOP_HOME/session.secret`
- `MEDIAMOP_SESSION_COOKIE_SECURE=false` is the default in the image so plain `http://localhost` works
- set `MEDIAMOP_SESSION_COOKIE_SECURE=true` only when all browser traffic is HTTPS

## Health

The image exposes `GET /health` and includes a Docker `HEALTHCHECK`.

## Release alignment

- `compose.yaml` defaults to `ghcr.io/jampat000/mediamop:latest`
- `.github/workflows/release.yml` publishes stable images on tagged releases

## What Docker does not do

The container starts MediaMop. It does not:

- install Sonarr, Radarr, Emby, Jellyfin, or Plex
- configure reverse proxies or HTTPS for you
- replace local development docs for source work

## Related files

- `Dockerfile`
- `compose.yaml`
- `.github/workflows/release.yml`
