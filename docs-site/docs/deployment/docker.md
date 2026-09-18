---
sidebar_position: 1
title: Docker
---

# Docker Deployment

Weir runs on any machine with Docker, including Synology, Unraid, TrueNAS and Raspberry Pi. Both
64-bit Intel/AMD and ARM are supported.

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

Open **http://your-server-ip:9347** and create your account. That's it.

`./weir-data` holds Weir's database, settings, logs and backups. Keep it and you keep everything.

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

- **`/srv/media`** is where your media lives on the host. Change it to your own path.
- **`/media`** is where Weir sees it. Use `/media/...` paths when you set up folders in Weir.
- **`WEIR_PUID` / `WEIR_PGID`** make Weir read and write files as that user, so it can move them.
  Run `id your-username` on the host to find the numbers. On Synology it's usually `1026` /
  `100`, on Unraid `99` / `100`.

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

## What's in the image

- Images are published for **linux/amd64** and **linux/arm64** (`ghcr.io/jampat000/weir:latest` and `:X.Y.Z`)
- A self-contained .NET server, with the bundled web UI
- ffmpeg, mkvmerge (MKVToolNix), curl and gosu on a slim Debian base
- Runs as the `weir` user (UID/GID 1000 by default, or whatever `WEIR_PUID`/`WEIR_PGID` you set)
- Data volume `/data/weir`, port `9347`
- A built-in health check on `/health`

## Persisting data

Persist `/data/weir` on a durable volume — that's what `./weir-data` or `weir-data:` does in the
recipes above — so the database, settings, logs and backups survive a container replacement. Keep
`WEIR_SESSION_SECRET` stable across upgrades so browser sessions remain valid; if you don't set
one, Weir generates one and keeps it in that same volume.

## Common changes

| I want to… | Do this |
| --- | --- |
| Use a different port | Change the left number: `"8080:9347"` puts Weir at `http://your-server-ip:8080` |
| Pin a version instead of `latest` | `image: ghcr.io/jampat000/weir:3.0.1` |
| Use HTTPS through a reverse proxy | Set `WEIR_SESSION_COOKIE_SECURE=true` and `WEIR_TRUSTED_PROXY_IPS=<your proxy's IP>`. See [Reverse proxy](reverse-proxy) |
| Protect saved API keys with their own secret | Set `WEIR_CREDENTIALS_SECRET` to a long random value (`openssl rand -hex 32`) **before** you add Sonarr or Radarr |
| Use a GPU | See [hardware acceleration](https://github.com/jampat000/Weir/blob/main/docker/README.md#hardware-acceleration-and-device-passthrough) in the Docker reference. It's optional; Weir doesn't re-encode, so you usually don't need it |

Every variable Weir reads is documented in the [Docker reference](https://github.com/jampat000/Weir/blob/main/docker/README.md).

## What Docker does not do

The container starts Weir. It does not:

- install Sonarr, Radarr, Emby, Jellyfin, or Plex
- configure reverse proxies or HTTPS for you
- run more than one Weir server process against the same database — never point two containers at the same SQLite data
