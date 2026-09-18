---
sidebar_position: 1
title: Quickstart
---

# Quickstart

Get Weir running and clean your first file in a few minutes.

Weir is a self-hosted app: it watches a folder for new movie and TV files, removes the audio
tracks and subtitles you don't want, and puts the result in an output folder. Everything it
needs — including ffmpeg and MKVToolNix — comes bundled with it. There's nothing else to
install.

## 1. Install Weir

Pick whichever fits where you run it.

### Docker (Synology, Unraid, TrueNAS, Raspberry Pi, Linux servers)

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

This gets you a working Weir you can sign in to. It doesn't yet have your media folders — add
those once you're ready; see [Docker deployment](deployment/docker) for the compose recipe that
mounts them, plus the recipe for running Weir alongside Sonarr, Radarr and a download client.

### Windows

1. Download `Weir-win-Setup.exe` from the [latest release](https://github.com/jampat000/Weir/releases/latest).
2. Run it. You don't need admin rights.
3. Weir asks which port to use the first time it starts. Keep **9347** unless something else uses it.
4. Your browser opens Weir.

See the [Windows installer guide](deployment/windows) for what gets installed, how updates work,
and unattended installs.

## 2. Create your account

The first time you open Weir, it asks for a username and password. This creates the admin
account — there's no separate sign-up step.

## 3. Follow the setup wizard

The setup wizard has two parts:

- **Basics** — your time zone, and how compact you want the interface.
- **Libraries** — a **Watched folder** and an **Output folder** for Movies, and the same for TV.
  - **Watched folder**: where your downloads finish. Weir cleans whatever lands here.
  - **Output folder**: where Weir puts each cleaned file.

You can skip the wizard and set these later on the **Processing** page.

## 4. Choose what to keep

On **Processing**, set each library's audio and subtitle rules — for example, keep English and
Japanese audio, keep English subtitles, and drop commentary tracks.

## 5. Try it with a real file

Put a video file in a watched folder. Weir usually notices within seconds. On network shares and
in Docker it can take up to five minutes, because Weir falls back to checking on a timer instead
of relying on filesystem notifications.

- The file shows up on **Home** while Weir works on it.
- Once it's done, it shows up in **Activity**, and the cleaned copy is in the output folder.

Already have a library you want to clean up? Open **Processing → Library**, pick the library and
press **Scan now**. Weir shows you what it would remove and how much space that frees before it
changes anything.

## If nothing happens

| Problem | Try this |
| --- | --- |
| Files sit in the watched folder and nothing happens | In Docker, check the path in Weir is the path **inside the container**, not the path on the host. Weir can take up to five minutes to notice a file. |
| "Permission denied" in Activity | Set `WEIR_PUID` / `WEIR_PGID` to the user that owns your media folders. See [Docker deployment](deployment/docker). |
| Can't open Weir | Check the container is running and you're using the right port. Weir's health check is at `http://your-server-ip:9347/health`. |

## Next steps

- [Connecting Deluno, Sonarr and Radarr](guides/media-managers) — hand off files automatically
- [Docker deployment](deployment/docker) — media folders, file ownership, running alongside other apps
- [Windows installer](deployment/windows) — ports, updates, unattended installs
- [Building from source](guides/local-development) — for developers who want to run Weir from a clone
