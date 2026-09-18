---
sidebar_position: 2
title: Windows Installer
---

# Windows Installer

Weir ships a Velopack-based Windows package. It installs as a desktop app with a .NET system tray host and supports automatic delta updates.

## Installation

1. Download the setup exe from [GitHub Releases](https://github.com/jampat000/Weir/releases)
2. Run the installer (no admin required)
3. Launch **Weir** from the Start Menu or desktop shortcut

## What gets installed

| Component | Location |
|-----------|----------|
| Application binaries | `%LocalAppData%\Weir` |
| Tray app (the main program) | `Weir.exe` |
| Weir server | `server\WeirServer.exe` |
| Web UI | `server\web-dist` |
| Bundled ffmpeg | `server\bin\ffmpeg` |
| Bundled mkvmerge (MKVToolNix) | `server\bin\mkvtoolnix` |
| Runtime data (SQLite, logs, backups) | `C:\ProgramData\Weir` |

## How it runs

Weir runs in the user session, not as a Windows service. This avoids common NAS or external-drive access issues that affect Windows services.

The tray app (`Weir.exe`) starts the Weir server (`server\WeirServer.exe`, a self-contained .NET program) as a child process with `--port <port>`. It watches the server and restarts it if it stops unexpectedly. The server creates or updates its SQLite database itself when it starts.

The tray icon provides:
- **Open Weir** — opens the web UI in your browser
- **Open Data Folder** — opens the runtime data directory
- **Check for updates** — checks directly in installed builds or opens **Settings → Upgrade** when install metadata is unavailable
- **Quit** — stops Weir

## Updates

Updates are managed automatically by the .NET tray app via Velopack:

- Delta updates keep downloads small
- Automatic rollback on update failure
- No admin privileges required for updates
- Update behavior is configurable (auto, download-only, notify-only)

## Ports

| Service | Port | Scope |
|---------|------|-------|
| Main server | 8788 | LAN (0.0.0.0) |

## Migrating from legacy installs

If you have a previous Weir install that used the older setup program (installed under `C:\Program Files\Weir`), the new tray app automatically detects and cleans up the legacy updater service on first launch. Runtime data under `C:\ProgramData\Weir` is preserved.
