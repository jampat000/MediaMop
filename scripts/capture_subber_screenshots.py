"""Capture Subber UI screenshots.

Starts a temporary SQLite home, migrates, seeds ``alice`` / ``test-password-strong``,
runs API on a free localhost port (default scan from 18788) plus a **dedicated** Vite dev
server on another free port (default scan from 18880), signs in through the real login form,
then saves one full-page PNG per Subber tab under ``<repo>/screenshots/subber``.

Using a non-default web port avoids the common failure mode where port ``8782`` is already
taken by a normal ``npm run dev`` session: Vite would exit immediately (``strictPort``) while
this script would still probe ``8782`` successfully and talk to the wrong server.

Requires: ``playwright`` (``py -m playwright install chromium``).

Optional env:
  SUBBER_SHOT_BASE       — full web origin; when unset, ``http://127.0.0.1:<free>`` is chosen automatically
  SUBBER_SHOT_WEB_PORT   — first port to try when auto-picking the web port (default ``18880``)
  SUBBER_SHOT_OUT        — output directory (default ``<repo>/screenshots/subber``)
  SUBBER_SHOT_API_PORT   — API bind port (default ``18788``); avoids collisions with a dev API on 8788
"""

from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "apps" / "backend"
WEB = REPO / "apps" / "web"

# Absolute MEDIAMOP_DB_PATH (etc.) in the parent shell overrides MEDIAMOP_HOME for the DB file.
_RUNTIME_PATH_ENV_KEYS = (
    "MEDIAMOP_DB_PATH",
    "MEDIAMOP_BACKUP_DIR",
    "MEDIAMOP_LOG_DIR",
    "MEDIAMOP_TEMP_DIR",
)


def _pick_api_port() -> int:
    """Prefer ``SUBBER_SHOT_API_PORT``; otherwise scan from 18788 so we do not hit a stray dev API."""

    raw = (os.environ.get("SUBBER_SHOT_API_PORT") or "").strip()
    start = int(raw) if raw.isdigit() else 18788
    for port in range(start, start + 40):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            continue
        finally:
            s.close()
        return port
    msg = f"No free TCP port for screenshot API in range {start}..{start + 39}"
    raise RuntimeError(msg)


def _pick_web_port() -> int:
    """First free localhost TCP port for the screenshot Vite server (avoids colliding with ``8782`` dev)."""

    raw = (os.environ.get("SUBBER_SHOT_WEB_PORT") or "").strip()
    start = int(raw) if raw.isdigit() else 18880
    for port in range(start, start + 40):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            continue
        finally:
            s.close()
        return port
    msg = f"No free TCP port for screenshot web in range {start}..{start + 39}"
    raise RuntimeError(msg)


def _wait_http(url: str, *, timeout_s: float = 120.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)  # noqa: S310
            return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.35)
    msg = f"Timed out waiting for {url}"
    raise RuntimeError(msg)


def _pinned_runtime_env(home: Path) -> dict[str, str]:
    """Pin SQLite + dirs under ``home`` so ``apps/backend/.env`` cannot redirect Alembic/API/seed.

    ``alembic/env.py`` loads dotenv before resolving the DB URL; variables absent from the process
    environment are filled from ``.env``. Explicit paths here keep migrations, seeding, and
    uvicorn on the same temporary database.
    """

    h = home.resolve()
    return {
        "MEDIAMOP_DB_PATH": str((h / "data" / "mediamop.sqlite3").resolve()),
        "MEDIAMOP_BACKUP_DIR": str((h / "backups").resolve()),
        "MEDIAMOP_LOG_DIR": str((h / "logs").resolve()),
        "MEDIAMOP_TEMP_DIR": str((h / "temp").resolve()),
    }


def _seed_admin(home: Path) -> None:
    for k in _RUNTIME_PATH_ENV_KEYS:
        os.environ.pop(k, None)
    os.environ["MEDIAMOP_HOME"] = str(home.resolve())
    os.environ.update(_pinned_runtime_env(home))
    os.environ.setdefault("MEDIAMOP_SESSION_SECRET", "dev-session-secret-32-chars-minimum-x")
    sys.path[:0] = [str(BACKEND / "src"), str(BACKEND / "tests")]
    from integration_helpers import seed_admin_user  # noqa: PLC0415

    seed_admin_user()


def _which_node() -> str:
    import shutil

    n = shutil.which("node")
    if not n:
        msg = "Node.js not found on PATH (required to run Vite)."
        raise RuntimeError(msg)
    return n


def _playwright_failure_hint(page, out_dir: Path, tag: str) -> str:
    shot = out_dir / f"_capture-failure-{tag}.png"
    try:
        page.screenshot(path=str(shot), full_page=True)
    except Exception:
        shot = out_dir / "(screenshot failed)"
    try:
        alerts = page.locator('[role="alert"]').all_inner_texts()
    except Exception:
        alerts = []
    return f"url={page.url!r} alerts={alerts!r} screenshot={shot}"


def _stop_proc(p: subprocess.Popen[bytes] | None) -> None:
    if p is None or p.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            p.kill()
        else:
            p.send_signal(signal.SIGTERM)
        p.wait(timeout=15)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass


def _build_env_api(home: Path, base: str, secret: str) -> dict[str, str]:
    base_env = {k: v for k, v in os.environ.items() if k not in _RUNTIME_PATH_ENV_KEYS}
    return {
        **base_env,
        # Isolate from a developer shell that exports production-style auth flags.
        "MEDIAMOP_ENV": "development",
        "MEDIAMOP_SESSION_COOKIE_SECURE": "0",
        "MEDIAMOP_HOME": str(home.resolve()),
        **_pinned_runtime_env(home),
        "MEDIAMOP_SESSION_SECRET": secret,
        "MEDIAMOP_TRUSTED_BROWSER_ORIGINS": base,
        "PYTHONPATH": str(BACKEND / "src"),
        "MEDIAMOP_FETCHER_WORKER_COUNT": "0",
        "MEDIAMOP_REFINER_WORKER_COUNT": "0",
        "MEDIAMOP_PRUNER_WORKER_COUNT": "0",
        "MEDIAMOP_SUBBER_WORKER_COUNT": "0",
        "MEDIAMOP_SUBBER_LIBRARY_SCAN_SCHEDULE_ENQUEUE_ENABLED": "0",
        "MEDIAMOP_SUBBER_UPGRADE_SCHEDULE_ENQUEUE_ENABLED": "0",
        "MEDIAMOP_PRUNER_PREVIEW_SCHEDULE_ENQUEUE_ENABLED": "0",
        "MEDIAMOP_PRUNER_APPLY_ENABLED": "0",
        "MEDIAMOP_REFINER_SUPPLIED_PAYLOAD_EVALUATION_SCHEDULE_ENABLED": "0",
        "MEDIAMOP_REFINER_WATCHED_FOLDER_REMUX_SCAN_DISPATCH_SCHEDULE_ENABLED": "0",
        "MEDIAMOP_REFINER_WORK_TEMP_STALE_SWEEP_MOVIE_SCHEDULE_ENABLED": "0",
        "MEDIAMOP_REFINER_WORK_TEMP_STALE_SWEEP_TV_SCHEDULE_ENABLED": "0",
        "MEDIAMOP_REFINER_MOVIE_FAILURE_CLEANUP_SCHEDULE_ENABLED": "0",
        "MEDIAMOP_REFINER_TV_FAILURE_CLEANUP_SCHEDULE_ENABLED": "0",
        "MEDIAMOP_FAILED_IMPORT_RADARR_CLEANUP_DRIVE_SCHEDULE_ENABLED": "0",
        "MEDIAMOP_FAILED_IMPORT_SONARR_CLEANUP_DRIVE_SCHEDULE_ENABLED": "0",
        "MEDIAMOP_FETCHER_SONARR_MISSING_SEARCH_SCHEDULE_ENABLED": "0",
        "MEDIAMOP_FETCHER_SONARR_UPGRADE_SEARCH_SCHEDULE_ENABLED": "0",
        "MEDIAMOP_FETCHER_RADARR_MISSING_SEARCH_SCHEDULE_ENABLED": "0",
        "MEDIAMOP_FETCHER_RADARR_UPGRADE_SEARCH_SCHEDULE_ENABLED": "0",
    }


def main() -> int:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    out_dir = Path(os.environ.get("SUBBER_SHOT_OUT") or (REPO / "screenshots" / "subber"))
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_base = (os.environ.get("SUBBER_SHOT_BASE") or "").strip()
    if raw_base:
        u = urlparse(raw_base if "://" in raw_base else f"http://{raw_base}")
        if u.scheme not in ("http", "https") or u.hostname not in ("127.0.0.1", "localhost"):
            print("SUBBER_SHOT_BASE must be an http(s) URL for 127.0.0.1 or localhost.", file=sys.stderr)
            return 2
        if u.port is None:
            print("SUBBER_SHOT_BASE must include an explicit port (e.g. http://127.0.0.1:8782).", file=sys.stderr)
            return 2
        host = "127.0.0.1" if u.hostname == "localhost" else u.hostname
        web_port = u.port
        base = f"{u.scheme}://{host}:{u.port}".rstrip("/")
    else:
        web_port = _pick_web_port()
        base = f"http://127.0.0.1:{web_port}"

    home = Path(tempfile.mkdtemp(prefix="mm-subber-shot-"))
    secret = "dev-session-secret-32-chars-minimum-x"
    env_api = _build_env_api(home, base, secret)
    api_port = _pick_api_port()
    api_origin = f"http://127.0.0.1:{api_port}"

    api: subprocess.Popen[bytes] | None = None
    web: subprocess.Popen[bytes] | None = None
    try:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(BACKEND),
            env=env_api,
            check=True,
        )
        _seed_admin(home)

        api = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "mediamop.api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(api_port),
            ],
            cwd=str(BACKEND),
            env=env_api,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.2)
        if api.poll() is not None:
            msg = "uvicorn exited immediately (port bind failure?); check SUBBER_SHOT_API_PORT."
            raise RuntimeError(msg)
        node = _which_node()
        web_env = os.environ.copy()
        for k in _RUNTIME_PATH_ENV_KEYS:
            web_env.pop(k, None)
        # Same-origin `/api` via Vite proxy (session cookies must match the page origin).
        # Popping is not enough: Vite would still inject ``VITE_API_BASE_URL`` from ``.env*`` if unset.
        web_env["VITE_API_BASE_URL"] = ""
        # Bypass .env.development proxy overrides (see apps/web/vite.config.ts).
        web_env["MEDIAMOP_SCREENSHOT_API_PROXY_TARGET"] = api_origin
        web = subprocess.Popen(
            [
                node,
                str(WEB / "node_modules" / "vite" / "bin" / "vite.js"),
                "--host",
                "127.0.0.1",
                "--port",
                str(web_port),
                "--strictPort",
            ],
            cwd=str(WEB),
            env=web_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.6)
        if web.poll() is not None:
            msg = (
                "Vite exited immediately (port already in use?). "
                "Unset SUBBER_SHOT_BASE to auto-pick a free port, or free the port you passed."
            )
            raise RuntimeError(msg)

        _wait_http(f"{api_origin}/health")
        _wait_http(f"{base}/")

        tabs = ["Overview", "TV", "Movies", "Settings", "Schedule", "Jobs"]
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                base_url=base,
                viewport={"width": 1360, "height": 900},
                device_scale_factor=1,
            )
            page = context.new_page()
            try:
                page.goto("/login", wait_until="domcontentloaded", timeout=120_000)
                page.wait_for_selector('[data-testid="login-username"]', timeout=60_000)
                page.get_by_test_id("login-username").fill("alice")
                page.get_by_test_id("login-password").fill("test-password-strong")
                page.get_by_test_id("login-submit").click()
                try:
                    page.wait_for_url("**/app**", timeout=90_000)
                except PlaywrightTimeoutError as e:
                    raise RuntimeError(
                        "Timed out waiting for post-login navigation to /app. "
                        + _playwright_failure_hint(page, out_dir, "post-login-url"),
                    ) from e
                try:
                    page.wait_for_selector('[data-testid="shell-ready"]', timeout=90_000)
                except PlaywrightTimeoutError as e:
                    raise RuntimeError(
                        "Timed out waiting for authenticated shell. "
                        + _playwright_failure_hint(page, out_dir, "shell-ready"),
                    ) from e
                page.goto("/app/subber", wait_until="domcontentloaded", timeout=120_000)
                try:
                    page.wait_for_selector('[data-testid="subber-scope-page"]', timeout=60_000)
                except PlaywrightTimeoutError as e:
                    raise RuntimeError(
                        "Timed out waiting for Subber page. "
                        + _playwright_failure_hint(page, out_dir, "subber-page"),
                    ) from e
                for label in tabs:
                    page.get_by_role("tab", name=label).click()
                    time.sleep(0.45)
                    slug = label.lower().replace(" ", "-")
                    shot_path = out_dir / f"subber-{slug}.png"
                    page.screenshot(path=str(shot_path), full_page=True)
                    print(shot_path, file=sys.stderr)
            finally:
                browser.close()
    finally:
        _stop_proc(web)
        _stop_proc(api)
        shutil.rmtree(home, ignore_errors=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
