"""Verify a freshly installed Weir end to end over HTTP, so a release is ready to sign off on the
moment it lands on another machine.

Every check here goes through the same HTTP interface a browser on that network would use, so it
needs nothing on the target but a running Weir -- no remote shell. It was first written for a target
that had none (on 10.1.1.196, WinRM answered but refused authentication); other targets, such as
10.1.1.51, do accept WinRM, and this script works the same either way. HTTP is also the better test:
it exercises the artefact that actually ships, not a remoting stack.

Weir listens on 9347 unless its installer was told otherwise (the Windows tray asks on first run, or
takes --port / WEIR_PORT; Docker maps it with -p), so the base URL is usually http://<host>:9347.

Never types a password into a sign-in form, and never asks for one. Bootstrap only works on a fresh
install with no admin user yet, so this script always creates its own throwaway admin over the API
first, the same way scripts/screenshot-site.py does: GET /api/v1/auth/csrf, then
POST /api/v1/auth/bootstrap, then POST /api/v1/auth/login, all same-origin fetches with the session
cookie, using a generated secret that is never displayed and never typed anywhere. If the target
already has an admin user, this script stops immediately and says so -- it will not guess a password
or try anything else.

Checks (each one prints PASS, FAIL or SKIP with its evidence):

  1. It serves: GET /ready and GET /api/v1/system/readiness answer, and every readiness step is
     either ready or explains why not.
  2. It is the right build: the reported version is exactly 3.0.0.
  3. It is the right product: no "MediaMop" or "Refiner" anywhere in the served HTML, the built JS
     bundle, or any API response this run touched.
  4. The bundled media tools are present: ffmpeg, ffprobe and mkvmerge are all found. (The API only
     reports ffmpeg and mkvmerge by name -- see the check's own note on how ffprobe is covered.)
  5. Setup completes: bootstrap an admin, sign in, and clear the setup wizard over the API.
  6. Every screen renders in a real browser (Playwright): no error boundary, nothing blank, one
     screenshot per screen kept for the record.
  7. Optional: a real file processes. Pass --watched-folder, --output-folder and --sample-file
     (paths the *server* can see -- set those up on the target machine first) to add a library and
     confirm the sample file reaches a terminal, successful status. Off by default.

This script creates a library and an admin user on the target and leaves them there -- it does not
delete anything it did not create, and it never deletes media. It only ever reads or creates.

Usage (from the repository root, this machine, against the target's own address)::

    python -m pip install --require-hashes -r tests/requirements.txt
    python -m playwright install chromium   # once
    python scripts/verify-install.py http://<target-host>:9347

    # Opt into check 7 once folders exist on the target and it can see a sample file:
    python scripts/verify-install.py http://<target-host>:9347 \\
        --watched-folder "D:\\Media\\Incoming\\Movies" \\
        --output-folder "D:\\Media\\Library\\Movies" \\
        --sample-file "Some Movie (2024)/Some Movie.mkv"

Exit codes: 0 every check passed (skips do not count against this), 1 one or more checks failed,
2 verification could not proceed at all (the server never answered, or it already has an admin and
this script refused to guess a password).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import secrets
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

API = "/api/v1"
EXPECTED_VERSION = "3.0.0"
BANNED_NAMES = ("mediamop", "refiner")
CRASH_TEXT = "Something went wrong"
TIMEOUT_MS = 30_000
DESKTOP_VIEWPORT = {"width": 1440, "height": 1000}
READY_POLL_INTERVAL_S = 2.0
PROCESSING_POLL_INTERVAL_S = 3.0

# Terminal file statuses (Weir.Core.Processing.ProcessingFileStatuses): a successful run lands on
# one of these two -- "processed" (something changed) or "passed_through" (already matched the
# rules, handed back unchanged) -- a failed one lands on one of the other two.
SUCCESS_STATUSES = ("processed", "passed_through")
FAILURE_STATUSES = ("processing_failed", "blocked_upstream")


@dataclass(frozen=True)
class Screen:
    """One screen, addressed by its own URL -- no clicking through the UI to reach it."""

    index: int
    slug: str
    path: str
    ready_selector: str
    label: str


# The three screens that only exist for a moment in a fresh install's lifecycle. Driven with their
# own bespoke steps in main() (each needs the server in a specific state to reach it at all), but
# numbered here too so screenshots from every screen sort into one readable sequence.
SETUP_SCREEN = Screen(1, "setup", "/setup", '[data-testid="setup-form"]', "First-run setup")
LOGIN_SCREEN = Screen(2, "login", "/login", '[data-testid="login-form"]', "Login")
WIZARD_SCREEN = Screen(3, "setup-wizard", "/setup-wizard", '[data-testid="setup-wizard-skip"]', "Setup wizard")

# Every other screen the app has, addressed directly by its own path and query params, exactly as an
# operator's bookmark would. Kept in step with scripts/screenshot-site.py's screen list; if that list
# grows a screen, this one should too.
NORMAL_SCREENS: list[Screen] = [
    Screen(4, "home", "/", '[data-testid="shell-ready"]', "Home"),
    Screen(5, "activity", "/activity", '[data-testid="activity-feed"]', "Activity"),
    Screen(
        6,
        "processing-overview",
        "/processing?tab=overview",
        '[data-testid="processing-overview-panel"]',
        "Processing - Overview",
    ),
    Screen(
        7,
        "processing-libraries",
        "/processing?tab=libraries",
        '[data-testid="processing-libraries-section"]',
        "Processing - Libraries",
    ),
    Screen(
        8,
        "processing-audio-subtitles",
        "/processing?tab=audio-subtitles",
        '[data-testid="processing-rule-set-workspace"]',
        "Processing - Audio & subtitles",
    ),
    Screen(
        9,
        "processing-schedules",
        "/processing?tab=schedules",
        '[data-testid="processing-schedules-section"]',
        "Processing - Schedules",
    ),
    Screen(
        10,
        "processing-files",
        "/processing?tab=files",
        '[data-testid="processing-files-section"]',
        "Processing - Files",
    ),
    Screen(
        11,
        "processing-library-overview",
        "/processing?tab=library&view=overview",
        '[data-testid="processing-scope-page"]',
        "Processing - Library - Overview",
    ),
    Screen(
        12,
        "processing-jobs",
        "/processing?tab=jobs",
        '[data-testid="processing-jobs-inspection-section"]',
        "Processing - Jobs",
    ),
    Screen(
        13,
        "processing-maintenance",
        "/processing?tab=maintenance",
        '[data-testid="processing-maintenance-section"]',
        "Processing - Maintenance",
    ),
    Screen(14, "settings", "/settings", '[data-testid="suite-settings-page"]', "Settings - General"),
    Screen(
        15,
        "settings-security",
        "/settings?tab=security",
        '[data-testid="suite-settings-security"]',
        "Settings - Security",
    ),
    Screen(
        16,
        "settings-backup",
        "/settings?tab=backup",
        '[data-testid="suite-settings-backup-tab"]',
        "Settings - Backup and restore",
    ),
    Screen(
        17,
        "settings-upgrade",
        "/settings?tab=upgrade",
        '[data-testid="suite-settings-upgrade-tab"]',
        "Settings - Upgrade",
    ),
    Screen(
        18,
        "settings-logs",
        "/settings?tab=logs",
        '[data-testid="suite-settings-logs"]',
        "Settings - Logs",
    ),
    Screen(
        19,
        "settings-media-managers",
        "/settings?tab=media-managers",
        '[data-testid="media-manager-add"]',
        "Settings - Media managers",
    ),
    Screen(
        20,
        "not-found",
        "/this-page-does-not-exist-weir-verify-install",
        "text=Page not found",
        "Not found",
    ),
]


# --- Reporting: one line per check, printed as it happens, plus a summary at the end -------------


class Report:
    def __init__(self) -> None:
        self.tags: list[str] = []

    def _emit(self, tag: str, name: str, detail: str) -> None:
        line = f"[{tag}] {name}"
        if detail:
            line += f" -- {detail}"
        print(line)
        self.tags.append(tag)

    def run(self, name: str, fn: Callable[[], tuple[bool, str]]) -> bool:
        """Call fn(); any exception it raises becomes a FAIL instead of crashing the run."""

        try:
            ok, detail = fn()
        except Exception as exc:  # noqa: BLE001 - a check's own failure is data, not a crash
            self._emit("FAIL", name, str(exc))
            return False
        self._emit("PASS" if ok else "FAIL", name, detail)
        return ok

    def skip(self, name: str, reason: str) -> None:
        self._emit("SKIP", name, reason)

    def fail(self, name: str, detail: str) -> None:
        self._emit("FAIL", name, detail)

    def summary(self) -> int:
        passed = self.tags.count("PASS")
        failed = self.tags.count("FAIL")
        skipped = self.tags.count("SKIP")
        print()
        print(f"Summary: {passed} passed, {failed} failed, {skipped} skipped ({len(self.tags)} checks)")
        return 1 if failed else 0


# --- HTTP, driven through the browser's own fetch so cookies, origin and CSRF all behave exactly as
# they would for a real operator (the same approach scripts/screenshot-site.py uses to sign in
# without ever typing a password into the login form) -----------------------------------------------

_FETCH_JS = """
async ({ path, method, payload }) => {
  const headers = { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" };
  const opts = { method: method || "GET", credentials: "include", headers };
  if (payload !== null && payload !== undefined) { opts.body = JSON.stringify(payload); }
  const res = await fetch(path, opts);
  const text = await res.text();
  return { status: res.status, text };
}
"""


class Client:
    """One signed-in browser session's worth of API calls, and every response body seen so far."""

    def __init__(self, page: Page) -> None:
        self.page = page
        self.sources: dict[str, str] = {}

    def raw(self, method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, str]:
        result = self.page.evaluate(_FETCH_JS, {"path": path, "method": method, "payload": payload})
        status, text = int(result["status"]), str(result["text"])
        self.sources[f"{method} {path}"] = text
        return status, text

    def json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, Any, str]:
        status, text = self.raw(method, path, payload)
        try:
            body = json.loads(text) if text else None
        except json.JSONDecodeError:
            body = None
        return status, body, text

    def csrf(self) -> str:
        status, body, text = self.json("GET", f"{API}/auth/csrf")
        token = (body or {}).get("csrf_token") if isinstance(body, dict) else None
        if status != 200 or not token:
            raise RuntimeError(f"GET {API}/auth/csrf failed: HTTP {status}: {text[:300]}")
        return str(token)


# --- Individual checks ----------------------------------------------------------------------------


def wait_for_ready(client: Client, timeout_s: float) -> tuple[bool, str]:
    deadline = time.monotonic() + timeout_s
    status, body, text = 0, None, ""
    while True:
        status, body, text = client.json("GET", "/ready")
        if isinstance(body, dict) and body.get("ready") is True:
            return True, f"ready=True status={body.get('status')!r} (HTTP {status})"
        if time.monotonic() >= deadline:
            break
        time.sleep(READY_POLL_INTERVAL_S)
    reported = body.get("status") if isinstance(body, dict) else None
    reported_ready = body.get("ready") if isinstance(body, dict) else None
    return (
        False,
        f"never became ready within {timeout_s:.0f}s (ready={reported_ready} status={reported!r} HTTP {status}): {text[:200]}",
    )


def check_detailed_readiness(client: Client) -> tuple[bool, str]:
    status, body, text = client.json("GET", f"{API}/system/readiness")
    if not isinstance(body, dict):
        raise RuntimeError(f"GET {API}/system/readiness failed: HTTP {status}: {text[:300]}")
    steps = body.get("steps") or []
    unexplained = [s for s in steps if s.get("status") != "ready" and not str(s.get("detail") or "").strip()]
    parts = ", ".join(f"{s.get('name')}={s.get('status')}" for s in steps)
    detail = f"ready={body.get('ready')} status={body.get('status')!r} steps=[{parts}]"
    if unexplained:
        names = ", ".join(str(s.get("name")) for s in unexplained)
        return False, f"{detail}; step(s) not ready with no explanation: {names}"
    return True, detail


def check_version(client: Client) -> tuple[bool, str]:
    status, body, text = client.json("GET", f"{API}/system/readiness")
    if not isinstance(body, dict):
        raise RuntimeError(f"GET {API}/system/readiness failed: HTTP {status}: {text[:300]}")
    version = str(body.get("version") or "")
    if version == EXPECTED_VERSION:
        return True, f"version={version}"
    return False, f"version mismatch: reported {version!r}, expected {EXPECTED_VERSION!r}"


def check_media_tools(client: Client) -> tuple[bool, str]:
    status, body, text = client.json("GET", f"{API}/system/media-tools")
    if not isinstance(body, dict):
        raise RuntimeError(f"GET {API}/system/media-tools failed: HTTP {status}: {text[:300]}")
    ffmpeg = str(body.get("ffmpeg") or "")
    mkvmerge = str(body.get("mkvmerge") or "")
    absent = {"", "not installed", "unknown"}
    ffmpeg_found = ffmpeg not in absent
    mkvmerge_found = mkvmerge not in absent
    # The endpoint only names ffmpeg and mkvmerge; there is no separate ffprobe field. Weir's own
    # tool resolver (MediaToolResolver.Resolve) requires ffmpeg and ffprobe to exist together in the
    # same directory and fails if either is missing, so a non-absent "ffmpeg" value here is also
    # proof that ffprobe was found -- there is no server-reported case where one exists without the
    # other.
    detail = f"ffmpeg={ffmpeg!r} (its presence also confirms ffprobe, resolved alongside it), mkvmerge={mkvmerge!r}"
    return (ffmpeg_found and mkvmerge_found), detail


def collect_static_sources(client: Client, base_url: str) -> None:
    """Pull the served HTML, its JS/CSS bundles and the OpenAPI document into client.sources."""

    _, html = client.raw("GET", "/")
    target_host = urlparse(base_url).netloc
    for match in re.finditer(r'(?:src|href)=["\']([^"\']+\.(?:js|css)[^"\']*)["\']', html):
        asset = match.group(1)
        if asset.startswith("http://") or asset.startswith("https://"):
            parsed = urlparse(asset)
            if parsed.netloc != target_host:
                continue  # a third-party asset (e.g. a font CDN), not part of this build
            asset = parsed.path
        if f"GET {asset}" not in client.sources:
            client.raw("GET", asset)
    client.raw("GET", "/openapi.json")


def check_product_identity(client: Client) -> tuple[bool, str]:
    hits: list[str] = []
    for label, text in client.sources.items():
        if not text:
            continue
        lowered = text.lower()
        for name in BANNED_NAMES:
            idx = lowered.find(name)
            if idx == -1:
                continue
            start, end = max(0, idx - 40), min(len(text), idx + len(name) + 40)
            snippet = " ".join(text[start:end].split())
            hits.append(f"{label}: found {name!r} near \u2026{snippet}\u2026")
    if hits:
        shown = hits[:8]
        more = f" (+{len(hits) - len(shown)} more)" if len(hits) > len(shown) else ""
        return False, "; ".join(shown) + more
    return (
        True,
        f"scanned {len(client.sources)} source(s) (served HTML, JS/CSS bundles, API responses, rendered pages); no match",
    )


def check_bootstrap_gate(client: Client) -> tuple[bool, str]:
    status, body, text = client.json("GET", f"{API}/auth/bootstrap/status")
    if not isinstance(body, dict):
        raise RuntimeError(f"GET {API}/auth/bootstrap/status failed: HTTP {status}: {text[:300]}")
    allowed = bool(body.get("bootstrap_allowed"))
    reason = str(body.get("reason") or "")
    if not allowed:
        return False, f"bootstrap_allowed=False (reason={reason!r}) -- an admin user already exists on this install"
    return True, f"bootstrap_allowed=True (reason={reason!r})"


def do_bootstrap(client: Client, username: str, password: str) -> tuple[bool, str]:
    token = client.csrf()
    status, body, text = client.json(
        "POST",
        f"{API}/auth/bootstrap",
        {
            "username": username,
            "password": password,
            "csrf_token": token,
        },
    )
    if status >= 400:
        raise RuntimeError(f"HTTP {status}: {text[:300]}")
    return True, f"created admin {username!r} (generated password, never displayed or typed)"


def do_login(client: Client, username: str, password: str) -> tuple[bool, str]:
    token = client.csrf()
    status, body, text = client.json(
        "POST",
        f"{API}/auth/login",
        {
            "username": username,
            "password": password,
            "csrf_token": token,
        },
    )
    if status >= 400:
        raise RuntimeError(f"HTTP {status}: {text[:300]}")
    return True, f"signed in as {username!r}"


def do_skip_setup_wizard(client: Client) -> tuple[bool, str]:
    status, settings, text = client.json("GET", f"{API}/suite/settings")
    if not isinstance(settings, dict):
        raise RuntimeError(f"GET {API}/suite/settings failed: HTTP {status}: {text[:300]}")
    payload = dict(settings)
    payload["csrf_token"] = client.csrf()
    payload["setup_wizard_state"] = "skipped"
    status2, body2, text2 = client.json("PUT", f"{API}/suite/settings", payload)
    if status2 != 200 or not isinstance(body2, dict):
        raise RuntimeError(f"PUT {API}/suite/settings failed: HTTP {status2}: {text2[:300]}")
    return True, f"setup_wizard_state={body2.get('setup_wizard_state')!r}"


def check_screen(client: Client, page: Page, base_url: str, screen: Screen, out_dir: Path) -> tuple[bool, str]:
    shot = out_dir / f"{screen.index:02d}-{screen.slug}.png"
    page.goto(base_url + screen.path, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
    try:
        page.wait_for_selector(screen.ready_selector, timeout=TIMEOUT_MS, state="visible")
    except PlaywrightTimeoutError:
        with contextlib.suppress(Exception):
            page.screenshot(path=str(shot), full_page=True)
        return (
            False,
            f"did not render its expected content ({screen.ready_selector}) within timeout; screenshot: {shot}",
        )
    with contextlib.suppress(Exception):
        page.wait_for_load_state("networkidle", timeout=3_000)
    page.wait_for_timeout(200)
    crash = page.get_by_text(CRASH_TEXT, exact=False)
    page.screenshot(path=str(shot), full_page=True)
    client.sources[f"DOM {screen.path}"] = page.content()
    if crash.count():
        return False, f"shows an error boundary ({crash.first.inner_text()!r}); screenshot: {shot}"
    return True, f"rendered; screenshot: {shot}"


def check_file_processing(
    client: Client, watched_folder: str, output_folder: str, sample_file: str, media_type: str, timeout_s: float
) -> tuple[bool, str]:
    token = client.csrf()
    name = f"verify-install-{secrets.token_hex(4)}"
    status, body, text = client.json(
        "POST",
        f"{API}/processing/libraries",
        {
            "csrf_token": token,
            "name": name,
            "media_type": media_type,
            "watched_folder": watched_folder,
            "output_folder": output_folder,
        },
    )
    if status not in (200, 201) or not isinstance(body, dict):
        raise RuntimeError(f"POST {API}/processing/libraries failed: HTTP {status}: {text[:300]}")
    library_id = body.get("id")
    if not library_id:
        raise RuntimeError(f"library {name!r} was created but the response had no id: {text[:300]}")

    deadline = time.monotonic() + timeout_s
    last_status = "(not seen yet)"
    query = f"{API}/processing/files?library_id={library_id}&path_contains={quote(sample_file)}"
    while time.monotonic() < deadline:
        status2, body2, text2 = client.json("GET", query)
        if status2 == 200 and isinstance(body2, dict):
            files = body2.get("files") or []
            match = next((f for f in files if sample_file in str(f.get("relative_path") or "")), None)
            if match:
                last_status = str(match.get("status"))
                if last_status in SUCCESS_STATUSES:
                    return True, f"library {name!r} (id={library_id}): {sample_file!r} reached {last_status!r}"
                if last_status in FAILURE_STATUSES:
                    return False, (
                        f"library {name!r} (id={library_id}): {sample_file!r} reached terminal failure "
                        f"{last_status!r} ({match.get('status_reason')!r})"
                    )
        time.sleep(PROCESSING_POLL_INTERVAL_S)
    return False, (
        f"library {name!r} (id={library_id}): {sample_file!r} did not reach a terminal status within "
        f"{timeout_s:.0f}s (last seen status: {last_status!r})"
    )


# --- CLI --------------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("base_url", help="The running Weir server's base URL, e.g. http://192.168.1.50:9347")
    parser.add_argument(
        "--screenshots-dir",
        type=Path,
        default=None,
        help="Directory to write one screenshot per screen into (default: ./verify-install-<timestamp>)",
    )
    parser.add_argument("--ready-timeout", type=float, default=90.0, help="Seconds to wait for /ready (default: 90)")
    processing = parser.add_argument_group(
        "optional check 7 (a real file processes)",
        "Give all three to opt in. The owner must set these folders up on the target machine first -- "
        "this script never creates folders or media, and never assumes a path exists.",
    )
    processing.add_argument("--watched-folder", help="A watched folder path the SERVER can see")
    processing.add_argument("--output-folder", help="An output folder path the SERVER can see")
    processing.add_argument(
        "--sample-file",
        help="The sample file's path relative to --watched-folder, e.g. 'Some Movie (2024)/Some Movie.mkv'",
    )
    processing.add_argument("--media-type", choices=["movie", "tv"], default="movie", help="Default: movie")
    processing.add_argument(
        "--processing-timeout", type=float, default=600.0, help="Seconds to wait for the file to finish (default: 600)"
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    base_url = args.base_url.strip().rstrip("/")
    if not re.match(r"^https?://", base_url):
        base_url = "http://" + base_url

    processing_args = (args.watched_folder, args.output_folder, args.sample_file)
    if any(processing_args) and not all(processing_args):
        parser.error("--watched-folder, --output-folder and --sample-file must be given together (or not at all)")

    screenshots_dir: Path = args.screenshots_dir or Path(f"verify-install-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    print(f"Verifying Weir at {base_url}")
    print(f"Screenshots: {screenshots_dir.resolve()}")
    print()

    report = Report()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            context = browser.new_context(viewport=DESKTOP_VIEWPORT)
            context.set_default_timeout(TIMEOUT_MS)
            page = context.new_page()
            client = Client(page)

            # Load the app shell once so every fetch below is same-origin (matching a real browser),
            # and so a dead server fails loudly here instead of as forty separate timeouts below.
            try:
                page.goto(base_url + "/", wait_until="domcontentloaded", timeout=TIMEOUT_MS)
            except Exception as exc:  # noqa: BLE001 - reported as the first check's failure, not a crash
                report.fail("1a. GET /ready", f"could not reach {base_url}/: {exc}")
                print()
                print("ABORT: the server never answered. Nothing else can be checked.")
                report.summary()
                return 2

            report.run("1a. GET /ready", lambda: wait_for_ready(client, args.ready_timeout))

            fresh_install = report.run(
                "Preflight: install has no admin user yet (GET /api/v1/auth/bootstrap/status)",
                lambda: check_bootstrap_gate(client),
            )
            if not fresh_install:
                print()
                print(
                    "ABORT: this target is not a fresh install, so bootstrapping a throwaway admin is not "
                    "possible. Per the hard rule on credentials, this script will not guess a password or "
                    "try anything else. Point it at a fresh install and run again."
                )
                report.summary()
                return 2

            report.run(
                "6. Screen renders: First-run setup",
                lambda: check_screen(client, page, base_url, SETUP_SCREEN, screenshots_dir),
            )

            username = f"verify-install-{secrets.token_hex(4)}"
            password = secrets.token_urlsafe(24)  # generated, never displayed, never typed into a form

            bootstrapped = report.run(
                "5a. Bootstrap a throwaway admin", lambda: do_bootstrap(client, username, password)
            )

            report.run(
                "6. Screen renders: Login",
                lambda: check_screen(client, page, base_url, LOGIN_SCREEN, screenshots_dir),
            )

            signed_in = False
            if bootstrapped:
                signed_in = report.run(
                    "5b. Sign in as the throwaway admin", lambda: do_login(client, username, password)
                )
            else:
                report.skip("5b. Sign in as the throwaway admin", "bootstrap failed above")

            if signed_in:
                report.run(
                    "6. Screen renders: Setup wizard",
                    lambda: check_screen(client, page, base_url, WIZARD_SCREEN, screenshots_dir),
                )
                report.run("5c. Complete the setup wizard", lambda: do_skip_setup_wizard(client))
            else:
                report.skip("6. Screen renders: Setup wizard", "not signed in")
                report.skip("5c. Complete the setup wizard", "not signed in")

            if signed_in:
                report.run("1b. GET /api/v1/system/readiness detail", lambda: check_detailed_readiness(client))
                report.run("2. Reported version is 3.0.0", lambda: check_version(client))
                report.run(
                    "4. Bundled media tools are found (ffmpeg, ffprobe, mkvmerge)", lambda: check_media_tools(client)
                )

                for screen in NORMAL_SCREENS:
                    report.run(
                        f"6. Screen renders: {screen.label}",
                        lambda screen=screen: check_screen(client, page, base_url, screen, screenshots_dir),
                    )
            else:
                for name in (
                    "1b. GET /api/v1/system/readiness detail",
                    "2. Reported version is 3.0.0",
                    "4. Bundled media tools are found (ffmpeg, ffprobe, mkvmerge)",
                    *(f"6. Screen renders: {s.label}" for s in NORMAL_SCREENS),
                ):
                    report.skip(name, "not signed in")

            collect_static_sources(client, base_url)
            report.run("3. No trace of MediaMop or Refiner", lambda: check_product_identity(client))

            if not any(processing_args):
                report.skip(
                    "7. A real file processes (opt-in)",
                    "not requested -- pass --watched-folder, --output-folder and --sample-file to opt in",
                )
            elif not signed_in:
                report.skip("7. A real file processes (opt-in)", "not signed in")
            else:
                report.run(
                    "7. A real file processes (opt-in)",
                    lambda: check_file_processing(
                        client,
                        args.watched_folder,
                        args.output_folder,
                        args.sample_file,
                        args.media_type,
                        args.processing_timeout,
                    ),
                )
        finally:
            browser.close()

    return report.summary()


if __name__ == "__main__":
    sys.exit(main())
