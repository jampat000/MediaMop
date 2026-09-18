"""Screenshot every screen of Weir's web app, so a redesign can be reviewed by eye.

Brings up the .NET server against a fresh, disposable ``WEIR_HOME`` (twice: once left empty, once
seeded with representative data by plain SQL — see ``tests/e2e/weir/utils.py`` for the same pattern),
signs in without ever typing a password into the login form, and walks every screen the app has, in
both themes and at a desktop and a narrow width. Writes PNGs plus a ``contact-sheet.html`` to the
directory given on the command line, and prints a manifest.

This does not build anything. Before running it:

    (cd apps/web && npm ci && npm run build)
    dotnet build apps/server/src/Weir.Host

Usage (from the repository root)::

    python scripts/screenshot-site.py <output-dir>

Needs the Playwright browsers installed once: ``python -m playwright install chromium``.
"""

from __future__ import annotations

import argparse
import contextlib
import secrets
import shutil
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_contact_sheet import build_contact_sheet  # noqa: E402
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright  # noqa: E402
from tests.e2e.weir import _runtime as runtime  # noqa: E402
from tests.e2e.weir.utils import db_path_for_home  # noqa: E402

WEB_DIST = REPO_ROOT / "apps" / "web" / "dist"
SERVER_PROJECT = REPO_ROOT / "apps" / "server" / "src" / "Weir.Host"

DESKTOP_VIEWPORT = {"width": 1440, "height": 1000}
NARROW_VIEWPORT = {"width": 390, "height": 844}
WIDTHS: list[tuple[str, dict[str, int]]] = [
    ("desktop", DESKTOP_VIEWPORT),
    ("narrow", NARROW_VIEWPORT),
]
THEMES = ["dark", "light"]
THEME_STORAGE_KEY = "weir-app-theme"  # apps/web/src/lib/ui/app-theme.ts

CRASH_TEXT = "Something went wrong"
TIMEOUT_MS = 30_000


@dataclass
class Screen:
    """One screen to capture, addressed by its own URL — no clicking through the UI."""

    index: int
    slug: str
    path: str
    ready_selector: str
    label: str


# The three screens that only exist for a moment in a fresh install's lifecycle (first-run setup,
# a pre-session login, and the once-pending setup wizard). Captured with their own bespoke steps in
# run_scenario() rather than the plain goto-and-shoot loop below, but listed here too so the contact
# sheet can show them in the same review order as everything else.
GATED_SCREENS: list[Screen] = [
    Screen(1, "setup", "/setup", '[data-testid="setup-form"]', "First-run setup"),
    Screen(2, "login", "/login", '[data-testid="login-form"]', "Login"),
    Screen(3, "setup-wizard", "/setup-wizard", '[data-testid="setup-wizard-skip"]', "Setup wizard"),
]

# Every other screen the app has, in review order. Tabs and sub-views are addressed by their own
# query params (`?tab=`, `?view=`), exactly as an operator's bookmark would.
NORMAL_SCREENS: list[Screen] = [
    Screen(4, "in-hand", "/", '[data-testid="shell-ready"]', "In hand"),
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
        "processing-library-files",
        "/processing?tab=library&view=files",
        '[data-testid="library-files-section"]',
        "Processing - Library - Files",
    ),
    Screen(
        13,
        "processing-library-codecs",
        "/processing?tab=library&view=codecs",
        '[data-testid="processing-scope-page"]',
        "Processing - Library - Codecs",
    ),
    Screen(
        14,
        "processing-library-languages",
        "/processing?tab=library&view=languages",
        '[data-testid="processing-scope-page"]',
        "Processing - Library - Languages",
    ),
    Screen(
        15,
        "processing-library-problems",
        "/processing?tab=library&view=problems",
        '[data-testid="processing-scope-page"]',
        "Processing - Library - Problems",
    ),
    Screen(
        16,
        "processing-jobs",
        "/processing?tab=jobs",
        '[data-testid="processing-jobs-inspection-section"]',
        "Processing - Jobs",
    ),
    Screen(
        17,
        "processing-maintenance",
        "/processing?tab=maintenance",
        '[data-testid="processing-maintenance-section"]',
        "Processing - Maintenance",
    ),
    Screen(18, "settings", "/settings", '[data-testid="suite-settings-page"]', "Settings - General"),
    Screen(
        19,
        "settings-security",
        "/settings?tab=security",
        '[data-testid="suite-settings-security"]',
        "Settings - Security",
    ),
    Screen(
        20,
        "settings-backup",
        "/settings?tab=backup",
        '[data-testid="suite-settings-backup-tab"]',
        "Settings - Backup and restore",
    ),
    Screen(
        21,
        "settings-upgrade",
        "/settings?tab=upgrade",
        '[data-testid="suite-settings-upgrade-tab"]',
        "Settings - Upgrade",
    ),
    Screen(
        22,
        "settings-logs",
        "/settings?tab=logs",
        '[data-testid="suite-settings-logs"]',
        "Settings - Logs",
    ),
    Screen(
        23,
        "settings-notifications",
        "/settings?tab=notifications",
        '[data-testid="suite-settings-notifications"]',
        "Settings - Notifications",
    ),
    Screen(
        24,
        "settings-media-managers",
        "/settings?tab=media-managers",
        '[data-testid="media-manager-add"]',
        "Settings - Media managers",
    ),
    Screen(
        25,
        "not-found",
        "/this-page-does-not-exist-weir-screenshot-harness",
        "text=Page not found",
        "Not found",
    ),
]

ALL_SCREENS: list[Screen] = GATED_SCREENS + NORMAL_SCREENS


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def check_prerequisites() -> None:
    """Fail loudly and early rather than screenshotting whatever happens to be on disk."""

    if not (WEB_DIST / "index.html").is_file():
        fail("apps/web/dist is missing its build. Run this first:\n    (cd apps/web && npm ci && npm run build)")
    server_dlls = list((REPO_ROOT / "apps" / "server").glob("src/Weir.Host/bin/*/*/Weir.dll"))
    if not server_dlls:
        fail("The .NET server has not been built. Run this first:\n    dotnet build apps/server/src/Weir.Host")
    if shutil.which("dotnet") is None:
        fail("The dotnet CLI is not on PATH.")


def ledger_for_this_checkout() -> Path:
    """Match tests/e2e/weir/conftest.py: parallel worktrees must not reap each other's servers."""

    import hashlib
    import tempfile

    checksum = hashlib.sha1(str(REPO_ROOT.resolve()).encode("utf-8"), usedforsecurity=False).hexdigest()[:10]
    return Path(tempfile.gettempdir()) / f"weir-screenshot-servers-{checksum}.json"


runtime.LEDGER = ledger_for_this_checkout()


def start_weir_server(session_secret: str) -> tuple[runtime.Server, str, str]:
    """A fresh, disposable WEIR_HOME with its own server process. Caller must stop_server() it."""

    import os

    api_port = runtime.pick_free_port()
    home = runtime.run_home(None)
    api_internal = f"http://127.0.0.1:{api_port}"
    logs = Path(home) / "e2e-logs"
    env = {
        **os.environ,
        "WEIR_HOME": home,
        "WEIR_SESSION_SECRET": session_secret,
        "WEIR_CORS_ORIGINS": api_internal,
        "WEIR_WEB_DIST": str(WEB_DIST),
        # One throwaway admin and a handful of logins per server; do not let production rate
        # limits (10 bootstraps/hour, 10 sign-ins/minute) turn a screenshot run into a stuck run.
        "WEIR_BOOTSTRAP_RATE_MAX_ATTEMPTS": "10000",
        "WEIR_AUTH_LOGIN_RATE_MAX_ATTEMPTS": "10000",
    }
    env.pop("WEIR_ENV", None)
    command = [
        "dotnet",
        "run",
        "--project",
        str(SERVER_PROJECT),
        "--no-build",
        "--",
        "--host",
        "127.0.0.1",
        "--port",
        str(api_port),
    ]
    server = runtime.start_server(
        "Weir screenshot server",
        command,
        cwd=REPO_ROOT,
        env=env,
        port=api_port,
        url=f"{api_internal}/health",
        log_path=logs / "api.log",
    )
    runtime.wait_until_up(server, timeout_s=90.0)
    if not db_path_for_home(home).is_file():
        runtime.stop_server(server)
        fail(f"The server did not create its database at {db_path_for_home(home)}.")
    return server, home, api_internal


# --- Signing in without ever typing a password into the form ------------------------------------
# Bootstrap a throwaway admin over the API, then drive the session the same way the app's own login
# form does: /api/v1/auth/csrf, then /api/v1/auth/login, as a same-origin fetch with credentials
# included. Both run from the page's own origin so the session cookie lands the normal way.

_AUTH_FETCH_JS = """
async ({ path, payload }) => {
  const headers = { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" };
  const csrfRes = await fetch("/api/v1/auth/csrf", { credentials: "include", headers });
  const csrf = await csrfRes.json();
  const res = await fetch(path, {
    method: "POST",
    credentials: "include",
    headers,
    body: JSON.stringify({ ...payload, csrf_token: csrf.csrf_token }),
  });
  return { status: res.status, body: await res.text() };
}
"""


def api_bootstrap(page: Page, username: str, password: str) -> None:
    result = page.evaluate(
        _AUTH_FETCH_JS, {"path": "/api/v1/auth/bootstrap", "payload": {"username": username, "password": password}}
    )
    if result["status"] >= 400:
        fail(f"Bootstrapping the throwaway admin failed: HTTP {result['status']}: {result['body']}")


def api_login(page: Page, username: str, password: str) -> None:
    result = page.evaluate(
        _AUTH_FETCH_JS, {"path": "/api/v1/auth/login", "payload": {"username": username, "password": password}}
    )
    if result["status"] >= 400:
        fail(f"Signing in the throwaway admin failed: HTTP {result['status']}: {result['body']}")


# --- Theme: driven the way the app itself drives it ----------------------------------------------
# apps/web/src/main.tsx applies `data-mm-theme` from this same localStorage key before React ever
# renders (so there is no flash of the wrong theme) — the identical mechanism the top-bar toggle uses
# (persistAppTheme in apps/web/src/lib/ui/app-theme.ts). Setting the key an app-shell page already
# writes, before navigation, is that mechanism — not a CSS override.


def new_context(
    browser: Browser, *, theme: str, viewport: dict[str, int], storage_state: dict | None = None
) -> BrowserContext:
    ctx = browser.new_context(
        viewport=viewport,
        device_scale_factor=2,
        storage_state=storage_state,
        color_scheme=theme,
    )
    ctx.add_init_script(f"try {{ localStorage.setItem({THEME_STORAGE_KEY!r}, {theme!r}); }} catch (e) {{}}")
    ctx.set_default_timeout(TIMEOUT_MS)
    return ctx


@dataclass
class Shooter:
    output_dir: Path
    scenario: str
    manifest: list[str] = field(default_factory=list)

    def shoot(self, page: Page, screen_idx: int, slug: str, theme: str, width_name: str, label: str) -> None:
        crash = page.get_by_text(CRASH_TEXT, exact=False)
        if crash.count():
            fail(
                f"{label} ({self.scenario}/{theme}/{width_name}) shows an error boundary: {crash.first.inner_text()!r}"
            )
        name = f"{screen_idx:02d}-{slug}--{self.scenario}--{theme}--{width_name}.png"
        target = self.output_dir / name
        page.screenshot(path=str(target), full_page=True)
        self.manifest.append(f"{name}\t{label} ({self.scenario}, {theme}, {width_name})")
        print(f"  {name}")

    def goto_and_shoot(self, page: Page, base_url: str, screen: Screen, theme: str, width_name: str) -> None:
        page.goto(base_url + screen.path, wait_until="domcontentloaded")
        page.wait_for_selector(screen.ready_selector, timeout=TIMEOUT_MS, state="visible")
        # Activity's live feed and Processing's polling keep the network busy by design.
        with contextlib.suppress(Exception):
            page.wait_for_load_state("networkidle", timeout=3_000)
        page.wait_for_timeout(200)
        self.shoot(page, screen.index, screen.slug, theme, width_name, screen.label)


def remux_pass_detail(
    *,
    outcome: str,
    trigger: str,
    result: str,
    user_message: str,
    relative_path: str,
    source_size_bytes: int,
    output_size_bytes: int,
    audio_removed: int,
    subtitles_removed: int,
    media_scope: str = "movie",
    copied_without_remux: bool = False,
) -> str:
    """One finished pass's Activity detail, shaped like RemuxPassVisibility.ClipForActivity's output.

    The envelope keys (module/action/trigger/result/severity/counts/user_message) come from
    Observability.ActivityDetailEnvelope; the rest are the pass payload keys Processing -> Overview
    reads back out of it.
    """

    import json

    detail = {
        "module": "processing",
        "action": "remux",
        "trigger": trigger,
        "result": result,
        "severity": "info" if result == "success" else "error",
        "media_scope": media_scope,
        "media_scope_label": "Movie" if media_scope == "movie" else "TV",
        "counts": {"audio_removed": audio_removed, "subtitles_removed": subtitles_removed},
        "user_message": user_message,
        "ok": True,
        "outcome": outcome,
        "relative_media_path": relative_path,
        "source_size_bytes": source_size_bytes,
        "output_size_bytes": output_size_bytes,
    }
    if copied_without_remux:
        detail["output_copied_without_remux"] = True
    return json.dumps(detail)


def seed_representative_data(home: str) -> None:
    """Plain SQL against the server's own SQLite file — no fixtures added to the product.

    Follows tests/e2e/weir/utils.py's pattern: the server keeps running and does not cache these
    rows, so they show up the same way a second operator's process writing to the same file would.
    """

    conn = sqlite3.connect(str(db_path_for_home(home)), timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        with conn:
            conn.execute(
                "UPDATE libraries SET watched_folder = ?, work_folder = ?, output_folder = ?, "
                "schedule_hours_limited = 1, schedule_start = '01:00', schedule_end = '06:00' "
                "WHERE id = 1",
                (r"D:\Media\Incoming\Movies", r"D:\Media\Work\Movies", r"D:\Media\Library\Movies"),
            )
            conn.execute(
                "UPDATE libraries SET watched_folder = ?, work_folder = ?, output_folder = ? WHERE id = 2",
                (r"D:\Media\Incoming\TV", r"D:\Media\Work\TV", r"D:\Media\Library\TV"),
            )

            files = [
                (
                    1,
                    "Movies/Arrival of the Kestrel (2024)/Arrival of the Kestrel.mkv",
                    "unprocessed",
                    "",
                    8_400_000_000,
                ),
                (
                    1,
                    "Movies/Arrival of the Kestrel (2024)/Arrival of the Kestrel.remux.mkv",
                    "processing",
                    "",
                    8_400_000_000,
                ),
                (1, "Movies/Late Autumn Reprise (2023)/Late Autumn Reprise.mkv", "processed", "", 6_100_000_000),
                (
                    1,
                    "Movies/A Quiet Ledger (2022)/A Quiet Ledger.mkv",
                    "processing_failed",
                    "ffmpeg exited with a video stream error",
                    5_950_000_000,
                ),
                (
                    1,
                    "Movies/Harbor Static (2021)/Harbor Static.mkv",
                    "on_hold",
                    "waiting for the file to stop growing",
                    4_200_000_000,
                ),
                (2, "TV/Northline/Season 01/Northline.S01E01.mkv", "unprocessed", "", 1_800_000_000),
                (2, "TV/Northline/Season 01/Northline.S01E02.mkv", "processed", "", 1_750_000_000),
                (
                    2,
                    "TV/Northline/Season 01/Northline.S01E03.mkv",
                    "passed_through",
                    "already matches every rule",
                    1_820_000_000,
                ),
                (
                    2,
                    "TV/Coastal Drift/Season 02/Coastal Drift.S02E04.mkv",
                    "blocked_upstream",
                    "Sonarr has not confirmed the import yet",
                    1_600_000_000,
                ),
            ]
            conn.executemany(
                "INSERT INTO files (library_id, relative_path, status, status_reason, size_bytes) VALUES (?, ?, ?, ?, ?)",
                files,
            )

            jobs = [
                (
                    "screenshot-seed-remux-1",
                    "processing.file.remux_pass.v1",
                    '{"relative_media_path": "Movies/Arrival of the Kestrel (2024)/Arrival of the Kestrel.mkv", "media_scope": "movie"}',
                    "leased",
                ),
                (
                    "screenshot-seed-remux-2",
                    "processing.file.remux_pass.v1",
                    '{"relative_media_path": "Movies/Late Autumn Reprise (2023)/Late Autumn Reprise.mkv", "media_scope": "movie"}',
                    "completed",
                ),
                (
                    "screenshot-seed-remux-3",
                    "processing.file.remux_pass.v1",
                    '{"relative_media_path": "Movies/A Quiet Ledger (2022)/A Quiet Ledger.mkv", "media_scope": "movie"}',
                    "failed",
                ),
                (
                    "screenshot-seed-scan-1",
                    "processing.watched_folder.remux_scan_dispatch.v1",
                    '{"library_id": 2}',
                    "pending",
                ),
                (
                    "screenshot-seed-sweep-1",
                    "processing.work_temp_stale_sweep.v1",
                    "{}",
                    "completed",
                ),
            ]
            conn.executemany(
                "INSERT INTO jobs (dedupe_key, job_kind, payload_json, status, last_error) VALUES (?, ?, ?, ?, ?)",
                [(*row, "ffmpeg exited with a video stream error" if row[3] == "failed" else None) for row in jobs],
            )

            library_files = [
                (
                    1,
                    "Movies/Late Autumn Reprise (2023)/Late Autumn Reprise.mkv",
                    6_100_000_000,
                    "matches",
                    "hevc",
                    1080,
                    "1080p",
                    2,
                    1,
                    "eng DTS-HD 5.1, jpn AC3 2.0",
                    "eng SDH",
                    None,
                ),
                (
                    1,
                    "Movies/Harbor Static (2021)/Harbor Static.mkv",
                    4_200_000_000,
                    "would_change",
                    "h264",
                    1080,
                    "1080p",
                    3,
                    4,
                    "eng AC3 5.1, eng DTS 5.1, fra AC3 2.0",
                    "eng, eng SDH, fra, spa",
                    None,
                ),
                (
                    1,
                    "Movies/A Quiet Ledger (2022)/A Quiet Ledger.mkv",
                    5_950_000_000,
                    "cannot_process",
                    "mpeg4",
                    480,
                    "sd",
                    1,
                    0,
                    "eng AC3 2.0",
                    None,
                    "unreadable",
                ),
                (
                    1,
                    "Movies/Coldwater Run (2020)/Coldwater Run.mkv",
                    3_600_000_000,
                    "cannot_process",
                    "h264",
                    720,
                    "720p",
                    1,
                    0,
                    "eng AAC 2.0",
                    None,
                    "seeding",
                ),
                (
                    1,
                    "Movies/The Long Shore (2019)/The Long Shore.mkv",
                    12_500_000_000,
                    "matches",
                    "av1",
                    2160,
                    "4k",
                    2,
                    2,
                    "eng TrueHD 7.1, deu AC3 5.1",
                    "eng, deu",
                    None,
                ),
                (
                    1,
                    "Movies/Nightfall Junction (2018)/Nightfall Junction.mkv",
                    7_100_000_000,
                    "would_change",
                    "hevc",
                    2160,
                    "4k",
                    4,
                    6,
                    "eng DTS-HD 7.1, eng AC3 2.0 (commentary), spa AC3 5.1, jpn AAC 2.0",
                    "eng, eng SDH, spa, jpn, kor, por",
                    None,
                ),
                (
                    1,
                    "Movies/Static Harbor Redux (2017)/Static Harbor Redux.mkv",
                    5_400_000_000,
                    "cannot_process",
                    "h264",
                    1080,
                    "1080p",
                    0,
                    0,
                    None,
                    None,
                    "no_audio_left",
                ),
                (
                    1,
                    "Movies/Rented Silence (2016)/Rented Silence.mkv",
                    4_800_000_000,
                    "cannot_process",
                    "hevc",
                    1080,
                    "1080p",
                    2,
                    1,
                    "eng DTS 5.1, fra AC3 2.0",
                    "eng",
                    "manager_redownload",
                ),
            ]
            for row in library_files:
                (
                    library_id,
                    path,
                    size_bytes,
                    classification,
                    video_codec,
                    video_height,
                    resolution_class,
                    audio_track_count,
                    subtitle_track_count,
                    audio_summary,
                    subtitle_summary,
                    problem_kind,
                ) = row
                cur = conn.execute(
                    "INSERT INTO library_files (library_id, path, size_bytes, classification, video_codec, video_height, "
                    "resolution_class, audio_track_count, subtitle_track_count, audio_summary, subtitle_summary, problem_kind) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        library_id,
                        path,
                        size_bytes,
                        classification,
                        video_codec,
                        video_height,
                        resolution_class,
                        audio_track_count,
                        subtitle_track_count,
                        audio_summary,
                        subtitle_summary,
                        problem_kind,
                    ),
                )
                library_file_id = cur.lastrowid
                facets: list[tuple[str, str]] = [("video_codec", video_codec), ("resolution", resolution_class)]
                if audio_summary:
                    facets.append(("audio", audio_summary.split(",")[0].strip()))
                    for lang_token in audio_summary.split(","):
                        lang = lang_token.strip().split(" ")[0]
                        if lang:
                            facets.append(("audio_language", lang))
                if subtitle_summary:
                    for lang_token in subtitle_summary.split(","):
                        lang = lang_token.strip().split(" ")[0]
                        if lang:
                            facets.append(("subtitle_language", lang))
                for facet, value in {(f, v) for f, v in facets if v}:
                    conn.execute(
                        "INSERT OR IGNORE INTO library_file_facets (library_id, library_file_id, facet, value) VALUES (?, ?, ?, ?)",
                        (library_id, library_file_id, facet, value),
                    )

            # What a clean would actually remove from the two "would change" files, and what that
            # would give back. The Library tab's Overview leads with these (they are the numbers a
            # clean acts on), so a seed that left them at their 0 defaults would show the tab's
            # headline figure as an empty one.
            conn.executemany(
                "UPDATE library_files SET removed_audio_tracks = ?, removed_subtitle_tracks = ?, "
                "estimated_bytes_saved = ? WHERE library_id = 1 AND path = ?",
                [
                    (1, 2, 310_000_000, "Movies/Harbor Static (2021)/Harbor Static.mkv"),
                    (2, 4, 940_000_000, "Movies/Nightfall Junction (2018)/Nightfall Junction.mkv"),
                ],
            )

            # Processing -> Overview's "last 30 days" figures are not read off these rows' text: they
            # re-parse the detail of `processing.file_remux_pass_completed` events as the JSON envelope
            # RemuxPassHandler writes (see OverviewStatsStore.BuildAsync). A finished pass seeded as a
            # plain "job_completed" line therefore shows up in the feed and nowhere in the figures, which
            # is how a seeded install ended up reporting 0 files handed back and a 0% success rate beside
            # two files it had just handed back. So the two finished passes below carry the real event
            # type and the real envelope.
            activity = [
                (
                    "processing.file_remux_pass_completed",
                    "processing",
                    "Late Autumn Reprise finished",
                    remux_pass_detail(
                        outcome="live_output_written",
                        trigger="schedule",
                        result="success",
                        user_message="Late Autumn Reprise.mkv was processed successfully",
                        relative_path="Movies/Late Autumn Reprise (2023)/Late Autumn Reprise.mkv",
                        source_size_bytes=6_100_000_000,
                        output_size_bytes=5_870_000_000,
                        audio_removed=1,
                        subtitles_removed=0,
                    ),
                    "schedule",
                    "ok",
                ),
                (
                    "job_failed",
                    "processing",
                    "A Quiet Ledger could not be processed",
                    "ffmpeg exited with a video stream error",
                    "schedule",
                    "failed",
                ),
                (
                    "library_scan",
                    "library",
                    "Movies library scan finished",
                    "8 files scanned, 2 would change, 3 cannot be processed",
                    "manual",
                    "ok",
                ),
                (
                    "processing.file_remux_pass_completed",
                    "processing",
                    "Northline S01E02 finished",
                    remux_pass_detail(
                        outcome="live_skipped_not_required",
                        trigger="watched_folder",
                        result="success",
                        user_message="No changes needed for Northline.S01E02.mkv",
                        relative_path="TV/Northline/Season 01/Northline.S01E02.mkv",
                        source_size_bytes=1_750_000_000,
                        output_size_bytes=1_750_000_000,
                        audio_removed=0,
                        subtitles_removed=0,
                        media_scope="tv",
                        copied_without_remux=True,
                    ),
                    "watched_folder",
                    "ok",
                ),
                (
                    "connection_test",
                    "media_manager",
                    "Sonarr connection tested",
                    "Reachable, 214 series",
                    "manual",
                    "ok",
                ),
                (
                    "job_failed",
                    "processing",
                    "Coastal Drift S02E04 held",
                    "Sonarr has not confirmed the import yet",
                    "watched_folder",
                    "warning",
                ),
                (
                    "configuration_backup",
                    "suite",
                    "Configuration backup completed",
                    "12 tables, 480 KB",
                    "schedule",
                    "ok",
                ),
                (
                    "maintenance",
                    "suite",
                    "Stale work-file sweep completed",
                    "Removed 2 abandoned temp files",
                    "schedule",
                    "ok",
                ),
            ]
            conn.executemany(
                'INSERT INTO activity_events (event_type, module, title, detail, "trigger", result) VALUES (?, ?, ?, ?, ?, ?)',
                activity,
            )

            conn.execute(
                "INSERT INTO notification_channels (label, provider, url, events_json, enabled) VALUES (?, ?, ?, ?, ?)",
                ("Ops webhook", "generic", "https://example.invalid/hooks/weir", '["job_failed", "job_completed"]', 1),
            )
            conn.execute(
                "INSERT INTO media_manager_connections (kind, name, enabled, base_url, last_connection_test_ok, last_connection_test_detail) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("sonarr", "Sonarr (main)", 1, "http://127.0.0.1:8989", 1, "Reachable, 214 series"),
            )
    finally:
        conn.close()


def set_wizard_state(home: str, state: str) -> None:
    conn = sqlite3.connect(str(db_path_for_home(home)), timeout=30)
    try:
        with conn:
            conn.execute("UPDATE suite_settings SET setup_wizard_state = ?", (state,))
    finally:
        conn.close()


def run_scenario(browser: Browser, *, scenario: str, output_dir: Path) -> list[str]:
    print(f"\n=== scenario: {scenario} ===")
    session_secret = secrets.token_hex(32)
    server, home, base_url = start_weir_server(session_secret)
    shooter = Shooter(output_dir=output_dir, scenario=scenario)
    username = f"site-shots-{scenario}"
    password = secrets.token_urlsafe(24)  # generated, never typed into the login form
    try:
        # 1. Setup screen (first-run bootstrap form), before any admin exists — every combo.
        setup_screen = GATED_SCREENS[0]
        for theme in THEMES:
            for width_name, viewport in WIDTHS:
                ctx = new_context(browser, theme=theme, viewport=viewport)
                page = ctx.new_page()
                page.goto(base_url + setup_screen.path, wait_until="domcontentloaded")
                page.wait_for_selector(setup_screen.ready_selector, timeout=TIMEOUT_MS, state="visible")
                shooter.shoot(page, setup_screen.index, setup_screen.slug, theme, width_name, setup_screen.label)
                ctx.close()

        # 2. Bootstrap a throwaway admin over the API (never typed into the form).
        boot_ctx = new_context(browser, theme="dark", viewport=DESKTOP_VIEWPORT)
        boot_page = boot_ctx.new_page()
        boot_page.goto(base_url + "/", wait_until="domcontentloaded")
        api_bootstrap(boot_page, username, password)
        boot_ctx.close()

        # 3. Login screen, now that bootstrapping is no longer offered — every combo, unauthenticated.
        login_screen = GATED_SCREENS[1]
        for theme in THEMES:
            for width_name, viewport in WIDTHS:
                ctx = new_context(browser, theme=theme, viewport=viewport)
                page = ctx.new_page()
                page.goto(base_url + login_screen.path, wait_until="domcontentloaded")
                page.wait_for_selector(login_screen.ready_selector, timeout=TIMEOUT_MS, state="visible")
                shooter.shoot(page, login_screen.index, login_screen.slug, theme, width_name, login_screen.label)
                ctx.close()

        # 4. Sign in once (csrf, then login, same-origin fetch with credentials included) and keep
        # the resulting session cookie to replay into the other theme/width contexts below — that is
        # cookie reuse of one real session, not a second sign-in.
        auth_ctx = new_context(browser, theme="dark", viewport=DESKTOP_VIEWPORT)
        auth_page = auth_ctx.new_page()
        auth_page.goto(base_url + "/", wait_until="domcontentloaded")
        api_login(auth_page, username, password)
        storage_state = auth_ctx.storage_state()
        auth_ctx.close()

        # 5. Setup wizard: a fresh bootstrap always starts here. Capture every combo while it is
        # still pending, then move it out of the way for the rest of this scenario's screens.
        wizard_screen = GATED_SCREENS[2]
        for theme in THEMES:
            for width_name, viewport in WIDTHS:
                ctx = new_context(browser, theme=theme, viewport=viewport, storage_state=storage_state)
                page = ctx.new_page()
                page.goto(base_url + wizard_screen.path, wait_until="domcontentloaded")
                page.wait_for_selector(wizard_screen.ready_selector, timeout=TIMEOUT_MS, state="visible")
                shooter.shoot(page, wizard_screen.index, wizard_screen.slug, theme, width_name, wizard_screen.label)
                ctx.close()
        set_wizard_state(home, "skipped")

        if scenario == "seeded":
            seed_representative_data(home)

        # 6. Every remaining screen, addressed directly by its own URL and query params.
        for theme in THEMES:
            for width_name, viewport in WIDTHS:
                ctx = new_context(browser, theme=theme, viewport=viewport, storage_state=storage_state)
                page = ctx.new_page()
                for screen in NORMAL_SCREENS:
                    shooter.goto_and_shoot(page, base_url, screen, theme, width_name)
                ctx.close()
    finally:
        runtime.stop_server(server)
        shutil.rmtree(home, ignore_errors=True)
    return shooter.manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("output_dir", type=Path, help="Directory to write PNGs and contact-sheet.html into")
    args = parser.parse_args()

    check_prerequisites()

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    stopped = runtime.reap_leftovers()
    if stopped:
        print(f"Stopped servers left behind by an earlier run: {', '.join(stopped)}")

    manifest: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--force-color-profile=srgb"])
        try:
            for scenario in ("empty", "seeded"):
                manifest.extend(run_scenario(browser, scenario=scenario, output_dir=output_dir))
        finally:
            browser.close()

    build_contact_sheet(output_dir, ALL_SCREENS)

    manifest.sort()
    manifest_path = output_dir / "manifest.txt"
    manifest_path.write_text("\n".join(manifest) + "\n", encoding="utf-8")
    print(f"\n{len(manifest)} screenshots written to {output_dir}")
    print(f"Manifest: {manifest_path}")
    print(f"Contact sheet: {output_dir / 'contact-sheet.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
