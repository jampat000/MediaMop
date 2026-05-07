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

If you want to override defaults later, copy `docker/.env.example` to `.env.mediamop`
and run `docker compose --env-file .env.mediamop up -d`.

## Data and runtime settings

- `MEDIAMOP_HOME` defaults to `/data/mediamop`
- mount a volume if you want SQLite data and runtime files to persist
- if `MEDIAMOP_SESSION_SECRET` is not provided, the container generates one automatically and persists it to `$MEDIAMOP_HOME/session.secret`
- if you prefer to provide your own session secret, generate it with `openssl rand -hex 32`
- set `MEDIAMOP_CREDENTIALS_SECRET` to a different long random value before saving Pruner, Subber, Sonarr, or Radarr credentials
- changing `MEDIAMOP_SESSION_SECRET` can require re-entering any credentials that were still encrypted with the old session secret
- `MEDIAMOP_SESSION_COOKIE_SECURE=false` is the default in the image so plain `http://localhost` works
- set `MEDIAMOP_SESSION_COOKIE_SECURE=true` only when all browser traffic is HTTPS

## Docker ownership controls

The container starts as `root`, reconciles optional filesystem ownership, then launches
MediaMop as the unprivileged `mediamop` user. This keeps the app itself non-root while
allowing host-mounted media paths to be aligned with your NAS or Docker user strategy.

Available environment variables:

- `MEDIAMOP_PUID` / `PUID`
- `MEDIAMOP_PGID` / `PGID`
- `MEDIAMOP_CHOWN_WATCHED`
- `MEDIAMOP_CHOWN_TEMP`
- `MEDIAMOP_CHOWN_OUTPUT`
- `MEDIAMOP_DIR_MODE_WATCHED`
- `MEDIAMOP_DIR_MODE_TEMP`
- `MEDIAMOP_DIR_MODE_OUTPUT`

Defaults:

- `MEDIAMOP_PUID=1000`
- `MEDIAMOP_PGID=1000`
- all `MEDIAMOP_CHOWN_*` flags default to `false`
- directory modes are unset unless you opt in

The `MEDIAMOP_CHOWN_*` flags recursively chown the configured Refiner folders stored in
MediaMop settings:

- watched = Movies/TV watched folders
- temp = Movies/TV work folders
- output = Movies/TV output folders

The `MEDIAMOP_DIR_MODE_*` values are optional octal directory modes such as `2775`. When
set, they are applied recursively to directories only for the selected folder category.

Example:

```bash
docker run --rm \
  -p 8788:8788 \
  -v mediamop-data:/data/mediamop \
  -e MEDIAMOP_PUID=1001 \
  -e MEDIAMOP_PGID=1001 \
  -e MEDIAMOP_CHOWN_OUTPUT=true \
  -e MEDIAMOP_DIR_MODE_OUTPUT=2775 \
  ghcr.io/jampat000/mediamop:latest
```

Migration note:

- Existing containers keep working with no env changes.
- If your output or work folders are bind-mounted from the host and MediaMop cannot write to them,
  set `MEDIAMOP_PUID` / `MEDIAMOP_PGID` to the host owner and enable the matching `MEDIAMOP_CHOWN_*`
  flag for the folder category you want MediaMop to manage.
- Leave `MEDIAMOP_CHOWN_WATCHED=false` unless you explicitly want MediaMop to take ownership of
  your watched/download folders.

## Health

The image exposes `GET /health` and includes a Docker `HEALTHCHECK`.

## Release alignment

- `compose.yaml` defaults to `ghcr.io/jampat000/mediamop:latest`
- `.github/workflows/release.yml` publishes stable images on tagged releases
- maintainers do not need local Docker to ship releases; use `scripts/verify-docker-remote.ps1`
  or the tag-driven release workflow to run Docker build and smoke checks on GitHub-hosted runners

## What Docker does not do

The container starts MediaMop. It does not:

- install Sonarr, Radarr, Emby, Jellyfin, or Plex
- configure reverse proxies or HTTPS for you
- replace local development docs for source work

## Related files

- `Dockerfile`
- `compose.yaml`
- `docker/.env.example`
- `.github/workflows/release.yml`
