# Weir Docker

Weir publishes an all-in-one container image with:

- the Weir server (C# / .NET 10, a self-contained single-file build)
- bundled production web UI, ffmpeg and mkvmerge (MKVToolNix)
- SQLite runtime under `WEIR_HOME`

Images are published for `linux/amd64` and `linux/arm64`:

- `ghcr.io/jampat000/weir:latest`
- `ghcr.io/jampat000/weir:X.Y.Z` (the Git tag is `vX.Y.Z`; the image tag has no `v`)

This page is the full reference — every variable Weir reads, plus the recipes for common setups.
For a shorter walkthrough, see the [Quickstart](https://jampat000.github.io/Weir/quickstart) and
[Docker deployment](https://jampat000.github.io/Weir/deployment/docker) pages on the docs site.

## The quickest way

Make a folder, save this as `compose.yaml` inside it:

```yaml
services:
  weir:
    image: ghcr.io/jampat000/weir:latest
    container_name: weir
    ports:
      - "9347:9347"
    volumes:
      - ./weir-data:/data/weir
    restart: unless-stopped
```

Then run:

```bash
docker compose up -d
```

Open `http://localhost:9347/` and create your account.

`./weir-data` holds Weir's database, settings, logs and backups. Keep it and you keep everything.
No `.env` file or secrets are required to get started — Weir generates its own session secret on
first start and keeps it in that same volume.

## With your media folders

Weir can only clean files it can see, so give it your media folders. This is the setup most
people want:

```yaml
services:
  weir:
    image: ghcr.io/jampat000/weir:latest
    container_name: weir
    ports:
      - "9347:9347"
    environment:
      - WEIR_PUID=1000   # the user that owns your media folders
      - WEIR_PGID=1000   # that user's group
    volumes:
      - ./weir-data:/data/weir
      - /srv/media:/media
    restart: unless-stopped
```

- `/srv/media` is where your media lives on the host. Change it to your own path.
- `/media` is where Weir sees it. Use `/media/...` paths when you set up folders in Weir.
- `WEIR_PUID` / `WEIR_PGID` make Weir read and write files as that user, so it can move them. Run
  `id your-username` on the host to find the numbers. On Synology it's usually `1026` / `100`, on
  Unraid `99` / `100`.

## Alongside Sonarr, Radarr and a download client

If Weir works next to other apps, **give every container the same folders at the same paths**.
When one app tells another where a file is, that path has to mean the same thing in both.

```yaml
services:
  weir:
    image: ghcr.io/jampat000/weir:latest
    container_name: weir
    ports:
      - "9347:9347"
    environment:
      - WEIR_PUID=1000
      - WEIR_PGID=1000
    volumes:
      - ./weir-data:/data/weir
      - /srv/media:/media
    restart: unless-stopped

  sonarr:
    image: lscr.io/linuxserver/sonarr:latest
    environment:
      - PUID=1000
      - PGID=1000
    volumes:
      - ./sonarr-config:/config
      - /srv/media:/media        # same folder, same path as Weir
    ports:
      - "8989:8989"
    restart: unless-stopped

  qbittorrent:
    image: lscr.io/linuxserver/qbittorrent:latest
    environment:
      - PUID=1000
      - PGID=1000
    volumes:
      - ./qbittorrent-config:/config
      - /srv/media:/media        # same folder, same path again
    ports:
      - "8080:8080"
    restart: unless-stopped
```

A folder layout that works well:

```text
/srv/media
├── downloads/complete/movies   ← your download client finishes files here   (Weir's watched folder)
├── downloads/complete/tv
├── weir/movies                 ← Weir puts cleaned files here               (Weir's output folder)
├── weir/tv
├── movies                      ← your library
└── tv
```

## Port

Weir listens on **9347** inside the container — Weir's own default, which spells W-E-I-R on a phone
keypad.

Choose the port on your host with `-p <host port>:9347`, as in the recipes above. To reach Weir at
`http://<host>:8080/` instead, change the left-hand side: `"8080:9347"`.

You rarely need to change the port *inside* the container, but you can: set `PORT`, and publish that
port instead. The server reads `PORT` at startup, and the image's health check follows it.

```bash
docker run --rm \
  -e PORT=9400 \
  -p 9400:9400 \
  -v weir-data:/data/weir \
  ghcr.io/jampat000/weir:latest
```

With `network_mode: host` there is no `-p` mapping, so `PORT` is how you move Weir off 9347.

## `docker run` instead of Compose

```bash
docker pull ghcr.io/jampat000/weir:latest
docker run --rm \
  -p 9347:9347 \
  -v weir-data:/data/weir \
  ghcr.io/jampat000/weir:latest
```

If you want to override defaults with an env file instead of inline `environment:` entries, copy
`docker/.env.example` to `.env.weir` and run `docker compose --env-file .env.weir up -d`.

## Environment variables

### Secrets

| Variable | Purpose |
|---|---|
| `WEIR_SESSION_SECRET` | Signs session cookies and CSRF tokens. Optional — if you don't set it, the container generates a high-entropy secret on first start and keeps it at `$WEIR_HOME/session.secret`, so it survives restarts. Set your own with `openssl rand -hex 32` if you'd rather manage it yourself. Keep it stable across upgrades: changing it signs everyone out. |
| `WEIR_CREDENTIALS_SECRET` | Encrypts saved provider credentials (Sonarr, Radarr, and similar). Set this to a long random value (`openssl rand -hex 32`), separate from `WEIR_SESSION_SECRET`, **before** you add those connections. Changing it later can require re-entering credentials that were encrypted with the old value. |

### Paths

| Variable | Purpose |
|---|---|
| `WEIR_HOME` | Persistent data root inside the container. Defaults to `/data/weir`; the compose recipes above mount a volume here. Holds the SQLite database, settings, logs and backups. |

### Networking and security

| Variable | Purpose |
|---|---|
| `WEIR_SESSION_COOKIE_SECURE` | Whether the session cookie requires HTTPS. Defaults to `false` in the image, so plain `http://localhost` or LAN access works out of the box. Set to `true` only once every browser reaches Weir over HTTPS (typically through a reverse proxy). |
| `WEIR_TRUSTED_PROXY_IPS` | The IP or CIDR of your immediate reverse proxy. Needed before Weir will trust `X-Forwarded-For` for client IPs — set it alongside `WEIR_SESSION_COOKIE_SECURE=true` when you put Weir behind a proxy. |
| `WEIR_CORS_ORIGINS` | Allowed browser origins for credentialed cross-origin requests. Weir refuses to start with `WEIR_CORS_ORIGINS=*` — list real origins instead. |

### File ownership

The container starts as `root`, remaps the `weir` user, makes sure `WEIR_HOME` belongs to it,
then launches Weir as that unprivileged user. This keeps the app itself non-root while letting
host-mounted media paths match your NAS or Docker user strategy.

| Variable | Purpose |
|---|---|
| `WEIR_PUID` / `PUID` | The UID Weir runs as inside the container. Defaults to `1000`. Set it to the owner of your host media folders so Weir can read and write them. |
| `WEIR_PGID` / `PGID` | The matching GID. Defaults to `1000`. |
| `WEIR_CHOWN_OUTPUT` | When enabled, Weir applies `WEIR_FILE_MODE_OUTPUT` / `WEIR_DIR_MODE_OUTPUT` and the `WEIR_PUID`/`WEIR_PGID` ownership directly to each file or folder it publishes, right after it writes it. Off by default. Applies to files landing in your output folders; it does not touch your watched or work folders — set ownership on those yourself on the host, or choose a `WEIR_PUID`/`WEIR_PGID` that can already write to them. |
| `WEIR_FILE_MODE_OUTPUT` | The file permission mode Weir applies to published files when `WEIR_CHOWN_OUTPUT` is on, as an octal string (e.g. `664`). |
| `WEIR_DIR_MODE_OUTPUT` | The folder permission mode Weir applies to folders it creates for output, as an octal string (e.g. `775`, or `2775` to also set the group-sticky bit). A malformed value refuses to start, with a clear error. |

`WEIR_CHOWN_WATCHED`, `WEIR_CHOWN_TEMP`, `WEIR_DIR_MODE_WATCHED` and `WEIR_DIR_MODE_TEMP` are
still validated at startup (a typo still stops the container) but are not applied to anything —
the watched and work folders are never Weir's own output, so there's nothing to apply them to.
Set ownership and permissions on those host folders directly, or pick a `WEIR_PUID` / `WEIR_PGID`
that can already write to them.

### Image selection

| Variable | Purpose |
|---|---|
| `WEIR_DOCKER_IMAGE` | Overrides the image reference used by helper scripts and env-file workflows. Not read by the container itself. |

## Data and runtime settings

- `WEIR_HOME` defaults to `/data/weir`; mount a volume there if you want the database and runtime
  files to persist (every recipe above already does this).
- if `WEIR_SESSION_SECRET` is not provided, the container generates one automatically and persists
  it to `$WEIR_HOME/session.secret`
- set `WEIR_CREDENTIALS_SECRET` to a different long random value before saving Sonarr or Radarr
  credentials
- changing `WEIR_SESSION_SECRET` can require re-entering any credentials that were still encrypted
  with the old session secret
- `WEIR_SESSION_COOKIE_SECURE=false` is the default in the image so plain `http://localhost` works
- set `WEIR_SESSION_COOKIE_SECURE=true` only when all browser traffic is HTTPS

## Health

The image exposes `GET /health` and includes a Docker `HEALTHCHECK`.

## Hardware acceleration and device passthrough

Weir stream-copies, so hardware decoding is rarely on the critical path today. It is switched
**off** by default and nothing here is needed to run Processing.

`GET /api/v1/processing/hardware` reports what the ffmpeg inside the container was compiled with.
That is not the same as what your host offers — a method being listed does not prove a device is
present — and neither is visible to the container without passthrough.

**Intel QSV / AMD / VAAPI** need the render node:

```yaml
services:
  weir:
    devices:
      - /dev/dri:/dev/dri
```

The container user must be able to read it. On most hosts that means adding the container user to
the `render` group (`group_add: ["render"]`), or matching its gid.

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

Without passthrough, a library configured to use a device **falls back to software and records
why on the file** — it does not fail. That is the intended behaviour, so a misconfigured device
costs you speed rather than a failed pass. The reason is on the file's record and in its
processing log.

Per-vendor disables exist on each library for the case where auto-detection picks a device that is
present but wrong.

## Filesystem events on bind mounts

Processing watches its watched folders so a new file becomes a candidate within seconds, and runs
its periodic scan as a backstop. **Bind mounts frequently deliver no filesystem-change events**,
and neither do most SMB and NFS shares — the events happen on the host, and nothing forwards them
into the container.

This is expected and handled. When the watcher cannot start, Weir:

- falls back to the periodic scan, which finds every file exactly as it did before;
- logs the reason once, not once per tick;
- reports it on `GET /ready` (and `GET /api/v1/system/readiness`) under the `filesystem_watcher` step.

That step stays `ready`. Falling back is slower, not broken, and failing readiness would take a
working instance out of a load balancer over a delay.

If you would rather not be told about it for a given library, switch off **Watch this folder for
changes** on the Processing Libraries tab. To turn the watcher off for the whole instance, set
`WEIR_PROCESSING_WATCHER_ENABLED=0`.

When events *do* work, `WEIR_PROCESSING_WATCHER_DEBOUNCE_SECONDS` (default 3) controls how long
the tree must be quiet before a burst of writes becomes one scan.

## What not to do

- **Do not** run more than one Weir server process against the same database
- **Do not** run multiple containers against the same SQLite database
- **Do not** use `WEIR_CORS_ORIGINS=*` (rejected at startup)

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
