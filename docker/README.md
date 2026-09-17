# Weir Docker

Weir publishes an all-in-one container image with:

- the Weir server (C# / .NET 10, a self-contained single-file build)
- bundled production web UI and ffmpeg
- SQLite runtime under `WEIR_HOME`

Images are published for `linux/amd64` and `linux/arm64`.

The stable image tags are published by the release workflow:

- `ghcr.io/jampat000/weir:latest`
- `ghcr.io/jampat000/weir:X.Y.Z` (the Git tag is `vX.Y.Z`; the image tag has no `v`)

## Quick start

```bash
docker pull ghcr.io/jampat000/weir:latest
docker run --rm \
  -p 8788:8788 \
  -v weir-data:/data/weir \
  ghcr.io/jampat000/weir:latest
```

Open `http://localhost:8788/`.

## Compose

From the repository root:

1. Start Weir:

   ```bash
   docker compose pull
   docker compose up -d
   ```

2. Open `http://localhost:8788/`.

If you want to override defaults later, copy `docker/.env.example` to `.env.weir`
and run `docker compose --env-file .env.weir up -d`.

## Data and runtime settings

- `WEIR_HOME` defaults to `/data/weir`
- mount a volume if you want SQLite data and runtime files to persist
- if `WEIR_SESSION_SECRET` is not provided, the container generates one automatically and persists it to `$WEIR_HOME/session.secret`
- if you prefer to provide your own session secret, generate it with `openssl rand -hex 32`
- set `WEIR_CREDENTIALS_SECRET` to a different long random value before saving Sonarr or Radarr credentials
- changing `WEIR_SESSION_SECRET` can require re-entering any credentials that were still encrypted with the old session secret
- `WEIR_SESSION_COOKIE_SECURE=false` is the default in the image so plain `http://localhost` works
- set `WEIR_SESSION_COOKIE_SECURE=true` only when all browser traffic is HTTPS

## Docker ownership controls

The container starts as `root`, remaps the `weir` user, makes sure `WEIR_HOME` belongs to it,
then launches Weir as that unprivileged user. This keeps the app itself non-root while
letting host-mounted media paths match your NAS or Docker user strategy.

- `WEIR_PUID` / `PUID` (default `1000`)
- `WEIR_PGID` / `PGID` (default `1000`)

Set them to the owner of your host folders so Weir can read the watched folders and write the
work and output folders:

```bash
docker run --rm \
  -p 8788:8788 \
  -v weir-data:/data/weir \
  -e WEIR_PUID=1001 \
  -e WEIR_PGID=1001 \
  ghcr.io/jampat000/weir:latest
```

### Output ownership (#555)

`WEIR_CHOWN_OUTPUT`, `WEIR_FILE_MODE_OUTPUT` (a file mode, not just a directory mode) and
`WEIR_DIR_MODE_OUTPUT` are read at startup by the .NET server itself (validated then, with a
clear error for a malformed octal mode) and applied in-process to each output file or folder
right after Weir writes or creates it — see `apps/server/README.md`, "Output ownership (#555)".
This is a narrower, directly-applied replacement for the old Refiner path-ownership sweep, which
recursively chowned folders read from a path settings table that went away when folders moved
onto libraries (#363), so it had already stopped changing anything before the move to .NET.

`WEIR_CHOWN_WATCHED`/`WEIR_CHOWN_TEMP`/`WEIR_DIR_MODE_WATCHED`/`WEIR_DIR_MODE_TEMP` have no .NET
equivalent: the watched and work folders are never Weir's own output, so there is nothing for a
"just wrote this" hook to apply them to. They are still validated, so a typo stops the container,
but the entrypoint logs a line and ignores them. Fix ownership on the host instead.

`WEIR_PUID`/`PGID` still choose the container's own runtime user as described above; only the
output-folder policy is applied differently.

## Health

The image exposes `GET /health` and includes a Docker `HEALTHCHECK`.

## Hardware acceleration and device passthrough

Weir stream-copies, so hardware decoding is rarely on the critical path today. It is
switched **off** by default and nothing here is needed to run Refiner.

`GET /api/v1/refiner/hardware` reports what the ffmpeg inside the container was compiled
with. That is not the same as what your host offers — a method being listed does not prove
a device is present — and neither is visible to the container without passthrough.

**Intel QSV / AMD / VAAPI** need the render node:

```yaml
services:
  weir:
    devices:
      - /dev/dri:/dev/dri
```

The container user must be able to read it. On most hosts that means adding the container
user to the `render` group (`group_add: ["render"]`), or matching its gid.

**NVIDIA** needs the NVIDIA Container Toolkit on the host, then:

```yaml
services:
  weir:
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: ["gpu"]
```

Without passthrough, a library configured to use a device **falls back to software and
records why on the file** — it does not fail. That is the intended behaviour, so a
misconfigured device costs you speed rather than a failed pass. The reason is on the
file's record and in its processing log.

Per-vendor disables exist on each library for the case where auto-detection picks a device
that is present but wrong.

## Filesystem events on bind mounts

> **Not in the .NET server yet.** The filesystem watcher has not been ported: the server
> currently finds new files with the periodic watched-folder scan only, and readiness reports
> no watched libraries. The rest of this section describes the watcher's intended behaviour.

Refiner watches its watched folders so a new file becomes a candidate within seconds, and
runs its periodic scan as a backstop. **Bind mounts frequently deliver no inotify events**,
and neither do most SMB and NFS shares — the events happen on the host, and nothing
forwards them into the container.

This is expected and handled. When the watcher cannot start, Weir:

- falls back to the periodic scan, which finds every file exactly as it did before;
- logs the reason **once**, not once per tick;
- reports it on `GET /readiness` under the `filesystem_watcher` step.

That step stays `ready`. Falling back is slower, not broken, and failing readiness would
take a working instance out of a load balancer over a delay.

If you would rather not be told about it for a given library, switch off
**Watch this folder for changes** on the Refiner Libraries tab. To turn the watcher off
for the whole instance, set `WEIR_REFINER_WATCHER_ENABLED=0`.

When events *do* work, `WEIR_REFINER_WATCHER_DEBOUNCE_SECONDS` (default 3) controls how
long the tree must be quiet before a burst of writes becomes one scan.

## Release alignment

- `compose.yaml` defaults to `ghcr.io/jampat000/weir:latest`
- `.github/workflows/release.yml` publishes stable images on tagged releases
- maintainers do not need local Docker to ship releases; use `scripts/verify-docker-remote.ps1`
  or the tag-driven release workflow to run Docker build and smoke checks on GitHub-hosted runners

## What Docker does not do

The container starts Weir. It does not:

- install Sonarr, Radarr, Emby, Jellyfin, or Plex
- configure reverse proxies or HTTPS for you
- replace local development docs for source work

## Related files

- `Dockerfile`
- `compose.yaml`
- `docker/.env.example`
- `.github/workflows/release.yml`
