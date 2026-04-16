"""Boot API + Vite preview, bootstrap+login, screenshot every Refiner tab, write a zip.

Same prerequisites as ``capture_fetcher_ui_zip.py``.

Output: ``<repo>/artifacts/refiner-ui-tabs.zip`` (PNG files inside).
"""

from __future__ import annotations

import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "apps" / "backend" / "pyproject.toml").is_file():
            return parent
    raise RuntimeError("Cannot find repo root (apps/backend/pyproject.toml missing)")


REPO_ROOT = _repo_root()
BACKEND_DIR = REPO_ROOT / "apps" / "backend"
WEB_DIR = REPO_ROOT / "apps" / "web"
SRC_PATH = (BACKEND_DIR / "src").resolve()
ARTIFACTS_DIR = REPO_ROOT / "artifacts"
ZIP_PATH = ARTIFACTS_DIR / "refiner-ui-tabs.zip"

BOOTSTRAP_USER = "capture-refiner-ui"
BOOTSTRAP_PASS = "capture-ref-pass-min8"


def _pick_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _e2e_home() -> str:
    explicit = (os.environ.get("MEDIAMOP_CAPTURE_HOME") or "").strip()
    if explicit:
        return str(Path(explicit).expanduser().resolve())
    return str(Path(tempfile.mkdtemp(prefix="mediamop_capture_refiner_")))


def _truncate_auth_tables(home: str) -> None:
    src = str(SRC_PATH.resolve())
    code = (
        "import os, sys\n"
        "sys.path.insert(0, os.environ['MEDIAMOP_BACKEND_SRC'])\n"
        "os.environ['MEDIAMOP_HOME'] = os.environ['MEDIAMOP_E2E_TRUNCATE_HOME']\n"
        "from sqlalchemy import delete\n"
        "from mediamop.core.config import MediaMopSettings\n"
        "from mediamop.core.db import create_db_engine, create_session_factory\n"
        "from mediamop.platform.auth.models import User, UserSession\n"
        "settings = MediaMopSettings.load()\n"
        "eng = create_db_engine(settings)\n"
        "fac = create_session_factory(eng)\n"
        "with fac() as db:\n"
        "    db.execute(delete(UserSession))\n"
        "    db.execute(delete(User))\n"
        "    db.commit()\n"
        "eng.dispose()\n"
    )
    subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(BACKEND_DIR.resolve()),
        env={
            **os.environ,
            "MEDIAMOP_BACKEND_SRC": src,
            "MEDIAMOP_E2E_TRUNCATE_HOME": home,
            "PYTHONUTF8": "1",
        },
        check=True,
        encoding="utf-8",
        errors="replace",
    )


def _wait_http(url: str, *, timeout_s: float = 90.0) -> None:
    deadline = time.time() + timeout_s
    last: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
            time.sleep(0.25)
    raise RuntimeError(f"timeout waiting for {url}: {last!r}")


def _npm_args() -> list[str]:
    if sys.platform == "win32":
        npm = shutil.which("npm.cmd") or shutil.which("npm")
        if not npm:
            raise RuntimeError("npm not found on PATH (install Node.js LTS).")
        return [npm]
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("npm not found on PATH.")
    return [npm]


def _ensure_web_dist() -> None:
    if (WEB_DIR / "dist" / "index.html").is_file():
        return
    print("Building apps/web (dist/ missing)...", flush=True)
    subprocess.run(
        [*_npm_args(), "run", "build"],
        cwd=str(WEB_DIR),
        check=True,
        encoding="utf-8",
        errors="replace",
    )


def _ensure_playwright() -> None:
    try:
        import playwright  # noqa: F401
    except ImportError as e:
        raise SystemExit(
            "Install Playwright in this Python environment:\n"
            "  cd apps/backend && .\\.venv\\Scripts\\python -m pip install playwright\n"
            "  .\\.venv\\Scripts\\python -m playwright install chromium\n"
        ) from e


def _capture_zip() -> Path:
    _ensure_web_dist()
    _ensure_playwright()

    from playwright.sync_api import sync_playwright

    secret = (os.environ.get("MEDIAMOP_SESSION_SECRET") or "").strip() or secrets.token_hex(24)
    home = _e2e_home()
    api_port = _pick_loopback_port()
    web_port = _pick_loopback_port()
    web_origin = f"http://127.0.0.1:{web_port}"
    api_internal = f"http://127.0.0.1:{api_port}"

    env_base = {
        **os.environ,
        "MEDIAMOP_HOME": home,
        "MEDIAMOP_SESSION_SECRET": secret,
        "MEDIAMOP_CORS_ORIGINS": web_origin,
        "PYTHONPATH": str(SRC_PATH),
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    }

    print("Alembic upgrade + fresh auth DB...", flush=True)
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        env=env_base,
        check=True,
        encoding="utf-8",
        errors="replace",
    )
    _truncate_auth_tables(home)

    api_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "mediamop.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(api_port),
            "--log-level",
            "warning",
        ],
        cwd=str(BACKEND_DIR),
        env=env_base,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    web_proc: subprocess.Popen | None = None
    shot_dir = Path(tempfile.mkdtemp(prefix="refiner_shots_"))
    try:
        _wait_http(f"{api_internal}/health")

        web_env = {
            **os.environ,
            "VITE_DEV_API_PROXY_TARGET": api_internal,
        }
        web_proc = subprocess.Popen(
            [
                *_npm_args(),
                "run",
                "preview",
                "--",
                "--host",
                "127.0.0.1",
                "--port",
                str(web_port),
                "--strictPort",
            ],
            cwd=str(WEB_DIR),
            env=web_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _wait_http(web_origin, timeout_s=120.0)

        tabs: list[tuple[str, str]] = [
            ("01-overview", "Overview"),
            ("02-libraries", "Libraries"),
            ("03-audio-subtitles", "Audio & subtitles"),
            ("04-schedules", "Schedules"),
            ("05-jobs", "Jobs"),
        ]

        print(f"Capturing {len(tabs)} tabs -> {shot_dir}", flush=True)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                page.set_default_timeout(60_000)

                page.goto(f"{web_origin}/", wait_until="domcontentloaded")
                page.get_by_test_id("setup-username").fill(BOOTSTRAP_USER)
                page.get_by_test_id("setup-password").fill(BOOTSTRAP_PASS)
                page.get_by_test_id("setup-submit").click()
                page.wait_for_url("**/login", timeout=60_000)
                page.get_by_test_id("login-username").fill(BOOTSTRAP_USER)
                page.get_by_test_id("login-password").fill(BOOTSTRAP_PASS)
                page.get_by_test_id("login-submit").click()
                page.wait_for_url("**/app", timeout=60_000)
                page.get_by_test_id("sign-out").wait_for(state="visible", timeout=60_000)

                page.goto(f"{web_origin}/app", wait_until="domcontentloaded")
                page.get_by_role("link", name="Refiner", exact=True).click()
                page.wait_for_url("**/app/refiner", timeout=60_000)
                page.get_by_role("heading", name="Refiner", exact=True).wait_for(state="visible", timeout=60_000)
                tab_nav = page.get_by_role("navigation", name="Refiner sections")
                tab_nav.wait_for(state="visible", timeout=60_000)
                page.wait_for_timeout(500)

                for slug, tab_name in tabs:
                    tab_btn = tab_nav.get_by_role("tab", name=tab_name, exact=True)
                    tab_btn.click(timeout=60_000)
                    page.wait_for_timeout(800)
                    page.screenshot(path=str(shot_dir / f"{slug}.png"), full_page=True)
                    print(f"  wrote {slug}.png", flush=True)
            finally:
                browser.close()

        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        if ZIP_PATH.exists():
            ZIP_PATH.unlink()
        with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
            for png in sorted(shot_dir.glob("*.png")):
                zf.write(png, arcname=png.name)
        print(f"Zip written: {ZIP_PATH}", flush=True)
        return ZIP_PATH
    finally:
        if web_proc is not None:
            web_proc.terminate()
            try:
                web_proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                web_proc.kill()
        api_proc.terminate()
        try:
            api_proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            api_proc.kill()
        shutil.rmtree(shot_dir, ignore_errors=True)
        if not (os.environ.get("MEDIAMOP_CAPTURE_HOME") or "").strip():
            shutil.rmtree(home, ignore_errors=True)


def main() -> int:
    try:
        path = _capture_zip()
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print(str(path.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
