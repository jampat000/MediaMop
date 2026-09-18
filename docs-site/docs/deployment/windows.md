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
4. The first time Weir starts, it asks which port to use (see [Choosing the port](#choosing-the-port))

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
| Saved port | `C:\ProgramData\Weir\port.txt` |

## How it runs

Weir runs in the user session, not as a Windows service. This avoids common NAS or external-drive access issues that affect Windows services.

The tray app (`Weir.exe`) starts the Weir server (`server\WeirServer.exe`, a self-contained .NET program) as a child process with `--port <port>`. It watches the server and restarts it if it stops unexpectedly. The server creates or updates its SQLite database itself when it starts.

The tray icon provides:
- **Open Weir** — opens the web UI in your browser
- **Open Data Folder** — opens the runtime data directory
- **Change port** — moves Weir to a different port and restarts it (the current port is shown in the menu)
- **Check for updates** — checks directly in installed builds or opens **Settings → Upgrade** when install metadata is unavailable
- **Quit** — stops Weir

## Updates

Updates are managed automatically by the .NET tray app via Velopack:

- Delta updates keep downloads small
- Automatic rollback on update failure
- No admin privileges required for updates
- Update behavior is configurable (auto, download-only, notify-only)

## Choosing the port

The port is the number at the end of Weir's web address: with the default, Weir is at
`http://localhost:9347/` on the same computer, or `http://<computer-name>:9347/` from elsewhere on
your network. Weir's default is **9347** — it spells W-E-I-R on a phone keypad, and nothing else in a
typical media stack uses it.

| Service | Default port | Scope |
|---------|--------------|-------|
| Main server | 9347 | LAN (0.0.0.0) |

### On a desktop: Weir asks once

The installer (`Weir-win-Setup.exe`, built with Velopack) has no pages of its own to ask questions
on, so the tray asks instead, the first time it starts:

- **Use Weir's default port, 9347**, or **Use this port** and type your own.
- If another program on the computer already uses 9347, the window says so, and fills in the first
  free port above it.
- It will not accept a port that is not a whole number from 1 to 65535, or one another program is
  already using.
- **Quit** closes Weir without starting it; it asks again next time.

Your choice is saved in `C:\ProgramData\Weir\port.txt` and used on every start after that. Weir
never moves to a different port on its own: if the saved port is busy on a later start, it tells you
which port is busy and asks again. To move Weir later, use **Change port** in the tray menu; Weir
restarts on the new port and opens it in your browser. If the server cannot start on the new port,
Weir goes back to the old one and says so.

### Unattended and remote installs

The window only appears when a person is at a desktop to answer it. To choose the port without it,
supply the port one of these ways — each is used and saved, and no window is shown:

| How | Example |
|-----|---------|
| Pass it through the installer to Weir's first start | `Weir-win-Setup.exe -- --port 9400` |
| Start the tray with `--port` | `"%LocalAppData%\Weir\current\Weir.exe" --port 9400 --no-browser` |
| Set `WEIR_PORT` before Weir starts | `setx WEIR_PORT 9400` |

`--port` wins over `WEIR_PORT`, and both win over the saved port — so a `WEIR_PORT` left set in the
environment overrides **Change port** on every start. Use it for a one-off choice, or clear it
afterwards. A supplied port is honoured even if another program has it at that moment; the server
then fails to start and says why in the log, rather than Weir quietly picking another.

`Weir-win-Setup.exe --silent` installs without starting Weir at all (that is Velopack's behaviour),
so for a silent install run `Weir.exe --port <number> --no-browser` once afterwards.

If nothing is supplied and there is no desktop — a WinRM or SSH session, a scheduled task with no
logged-on user, a service — Weir never shows the window. It uses 9347, or the first free port above
it if 9347 is taken, saves that, and records which port it chose and why in
`C:\ProgramData\Weir\tray-host.log`. If a saved port is busy on a later start with no desktop,
Weir does not move and does not start; the log says which port is busy and how to choose another.

## Migrating from legacy installs

If you have a previous Weir install that used the older setup program (installed under `C:\Program Files\Weir`), the new tray app automatically detects and cleans up the legacy updater service on first launch. Runtime data under `C:\ProgramData\Weir` is preserved.
