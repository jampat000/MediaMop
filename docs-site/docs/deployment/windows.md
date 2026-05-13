---
sidebar_position: 2
title: Windows Installer
---

# Windows Installer

MediaMop ships a Velopack-based Windows package. It installs as a desktop app with a .NET system tray host and supports automatic delta updates.

## Installation

1. Download the setup exe from [GitHub Releases](https://github.com/jampat000/MediaMop/releases)
2. Run the installer (no admin required)
3. Launch **MediaMop** from the Start Menu or desktop shortcut

## What gets installed

| Component | Location |
|-----------|----------|
| Application binaries | `%LocalAppData%\MediaMop` |
| Runtime data (SQLite, logs, backups) | `C:\ProgramData\MediaMop` |

## How it runs

MediaMop runs in the user session, not as a Windows service. This avoids common NAS or external-drive access issues that affect Windows services.

The .NET tray app launches the Python backend server as a child process and manages the application lifecycle.

The tray icon provides:
- **Open MediaMop** — opens the web UI in your browser
- **Open Data Folder** — opens the runtime data directory
- **Quit** — stops MediaMop

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

If you have a previous MediaMop install that used the Inno Setup installer (installed under `C:\Program Files\MediaMop`), the new tray app automatically detects and cleans up the legacy updater service on first launch. Runtime data under `C:\ProgramData\MediaMop` is preserved.
