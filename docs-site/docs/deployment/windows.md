---
sidebar_position: 2
title: Windows Installer
---

# Windows Installer

`MediaMopSetup.exe` is the supported Windows release artifact. It installs MediaMop as a desktop app with a system tray host.

## Installation

1. Download `MediaMopSetup.exe` from [GitHub Releases](https://github.com/jampat000/MediaMop/releases)
2. Run as administrator
3. Launch **MediaMop** from the Start Menu or desktop shortcut

## What gets installed

| Component | Location |
|-----------|----------|
| Application binaries | `C:\Program Files\MediaMop` |
| Runtime data (SQLite, logs, backups) | `C:\ProgramData\MediaMop` |
| MediaMop Updater service | Windows service (auto-start) |

## How it runs

MediaMop runs in the user session, not as a Windows service. This avoids common NAS or external-drive access issues that affect Windows services.

The tray icon provides:
- **Open MediaMop** — opens the web UI in your browser
- **Open Data Folder** — opens the runtime data directory
- **Quit** — stops MediaMop

## Updater service

The installer includes the **MediaMop Updater** as a required component. After the initial admin install:

- Future upgrades can run remotely from **Settings > Upgrade**
- No need to re-run the installer for routine updates

### Upgrading from older installs

If you have a Windows install from before the updater service was added, run the latest `MediaMopSetup.exe` once as administrator. This one-time bootstrap is required before remote in-app upgrades will work.

## Ports

| Service | Port | Scope |
|---------|------|-------|
| Main server | 8788 | localhost |
| Updater service | 8791 | localhost only |
