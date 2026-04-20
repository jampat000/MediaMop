# Docker (alpha)

MediaMop ships an **optional all-in-one** image: FastAPI on port **8788**, SQLite under **`MEDIAMOP_HOME`**, and the production **web** bundle served from the same origin (so the UI uses `/api/v1` without CORS).

This path is **alpha** / best-effort. The primary release contract remains [release.md](release.md) (git tag + `mediamop-web-dist.zip`).

## Build locally

From the repository root:

```bash
docker build -t mediamop:local .
```

## Run locally

```bash
docker run --rm \
  -e MEDIAMOP_SESSION_SECRET='replace-with-a-long-random-secret-at-least-32-chars' \
  -p 8788:8788 \
  -v mediamop-home:/data/mediamop \
  mediamop:local
```

Open `http://localhost:8788/`. Data and SQLite live under `/data/mediamop` inside the container (override with **`MEDIAMOP_HOME`**).

## GitHub Container Registry (alpha)

Workflow **Docker alpha** (`.github/workflows/docker-alpha.yml`):

1. **Manual:** GitHub → **Actions** → **Docker alpha** → **Run workflow** → set **Image tag** (default `alpha`).
2. **Tag push:** Push a git tag matching `v*-alpha*` (e.g. `v0.1.0-alpha.1`) to build and push an image tagged with that ref name.

Images are pushed to:

`ghcr.io/<github-owner-lowercase>/<repo-lowercase>:<tag>`

Package visibility may default to **private** for the repo; adjust under **Packages** in GitHub settings if you want it public.

## Environment variables

| Variable | Required | Notes |
|----------|----------|--------|
| `MEDIAMOP_SESSION_SECRET` | **Yes** | Session signing; use a long random value. |
| `MEDIAMOP_HOME` | No | Defaults to `/data/mediamop`. |
| `PORT` | No | Uvicorn listen port (default **8788**). |
| `MEDIAMOP_WEB_DIST` | No | Set in the image to the bundled `dist/`; override only for debugging. |

Other tuning (workers, log level, etc.) follows [local-development.md](local-development.md) / `MediaMopSettings` env vars.
