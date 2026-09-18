"""Capture exactly the screenshots README.md publishes, at the sizes it already uses.

``screenshot-site.py`` is the review harness: every screen, both themes, both widths, twice,
full-page at a 2x device scale factor. That is the right shape for reviewing a redesign by eye and
the wrong shape for the README gallery, whose images are viewport-sized at a 1x device scale factor
(1440x900 on the desktop, 400x860 on the phone) and must stay that way or the gallery reflows.

So this script publishes a different frame of the same app: it imports the harness and reuses its
bring-up wholesale — the disposable ``WEIR_HOME``, the server process, the seeded data, the theme
mechanism, and the throwaway admin bootstrapped over the API (**no password is ever typed into the
login form**) — and only replaces the viewport, the device scale factor, and the list of shots.

It also captures the one frame the harness cannot: the processing record panel, which opens from a
button on a file's row rather than from a URL. That needs a processing record to exist, so this
script seeds one file log on top of the harness's own seeded data, shaped like the payload
``RemuxPassRunner`` writes for a successful live remux.

Before running it, from the repository root::

    (cd apps/web && npm ci && npm run build)
    dotnet build apps/server/src/Weir.Host
    python -m playwright install chromium   # once per machine

Then::

    python scripts/capture-readme-screenshots.py <output-dir>

Copy the results over ``screenshots/`` once they have been looked at.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import secrets
import shutil
import sqlite3
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def _load_harness():
    """Import scripts/screenshot-site.py, whose filename is not a legal module name."""

    path = Path(__file__).resolve().parent / "screenshot-site.py"
    spec = importlib.util.spec_from_file_location("weir_screenshot_site", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise SystemExit(f"Could not load the screenshot harness from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


harness = _load_harness()

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright  # noqa: E402
from tests.e2e.weir.utils import db_path_for_home  # noqa: E402

# What README.md's images already are. Checked with a PNG header read before anything was reshot;
# keep them here so a later refresh does not quietly resize the gallery.
DESKTOP_VIEWPORT = {"width": 1440, "height": 900}
PHONE_VIEWPORT = {"width": 400, "height": 860}
DEVICE_SCALE_FACTOR = 1

# The file the harness seeds as `processed`, and so the one whose processing record can be opened.
RECORD_FILE = "Movies/Late Autumn Reprise (2023)/Late Autumn Reprise.mkv"


def readme_shots() -> list[tuple[str, str, str, dict[str, int]]]:
    """(published name, path, theme, viewport) for every image the README links, bar the record."""

    return [
        ("in-hand.png", "/", "dark", DESKTOP_VIEWPORT),
        ("in-hand-light.png", "/", "light", DESKTOP_VIEWPORT),
        ("in-hand-mobile.png", "/", "dark", PHONE_VIEWPORT),
        ("activity.png", "/activity", "dark", DESKTOP_VIEWPORT),
        ("processing.png", "/processing?tab=overview", "dark", DESKTOP_VIEWPORT),
        ("library.png", "/processing?tab=library&view=overview", "dark", DESKTOP_VIEWPORT),
        ("settings.png", "/settings", "dark", DESKTOP_VIEWPORT),
    ]


READY_SELECTORS = {
    "/": '[data-testid="shell-ready"]',
    "/activity": '[data-testid="activity-feed"]',
    "/processing?tab=overview": '[data-testid="processing-overview-panel"]',
    "/processing?tab=library&view=overview": '[data-testid="processing-scope-page"]',
    "/settings": '[data-testid="suite-settings-page"]',
    "/processing?tab=files": '[data-testid="processing-files-section"]',
}


def new_context(browser: Browser, *, theme: str, viewport: dict[str, int], storage_state: dict) -> BrowserContext:
    """The harness's context, at the README's device scale factor instead of the reviewer's."""

    ctx = browser.new_context(
        viewport=viewport,
        device_scale_factor=DEVICE_SCALE_FACTOR,
        storage_state=storage_state,
        color_scheme=theme,
    )
    ctx.add_init_script(
        f"try {{ localStorage.setItem({harness.THEME_STORAGE_KEY!r}, {theme!r}); }} catch (e) {{}}"
    )
    ctx.set_default_timeout(harness.TIMEOUT_MS)
    return ctx


def settle(page: Page, ready_selector: str) -> None:
    import contextlib

    page.wait_for_selector(ready_selector, timeout=harness.TIMEOUT_MS, state="visible")
    with contextlib.suppress(Exception):
        page.wait_for_load_state("networkidle", timeout=3_000)
    page.wait_for_timeout(300)


def refuse_a_broken_frame(page: Page, name: str) -> None:
    """A screenshot of an error boundary is worse than the stale one it would replace."""

    crash = page.get_by_text(harness.CRASH_TEXT, exact=False)
    if crash.count():
        harness.fail(f"{name} shows an error boundary: {crash.first.inner_text()!r}")


def quiesce_seeded_work(home: str) -> dict[str, list[tuple]]:
    """Stop the live worker from running the seeded jobs, and snapshot what it must not change.

    The harness seeds one `leased` remux job and one `pending` scan job because the Jobs screen
    needs both states. A real server then does the honest thing with them: it reclaims the expired
    lease, tries to remux a file that does not exist on this machine, and files a genuine failure.
    That failure is true about the screenshot machine and false about Weir — it turned Processing's
    success rate into 0% and put "worker failure" at the top of Activity.

    So the lease is renewed (a job in flight stays in flight) and the pending job is scheduled for
    later (a queued job stays queued). Both keep the status the Jobs screen is meant to show while
    the worker leaves them alone.
    """

    conn = sqlite3.connect(str(db_path_for_home(home)), timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        with conn:
            conn.execute("UPDATE jobs SET lease_expires_at = datetime('now', '+1 day') WHERE status = 'leased'")
            conn.execute("UPDATE jobs SET not_before = datetime('now', '+1 day') WHERE status = 'pending'")
        return {
            "activity_max_id": conn.execute("SELECT COALESCE(MAX(id), 0) FROM activity_events").fetchone()[0],
            "files": conn.execute(
                "SELECT id, status, status_reason, failure_attempts, failure_class, last_attempt_at, next_retry_at FROM files"
            ).fetchall(),
            "jobs": conn.execute(
                "SELECT id, status, last_error, attempt_count, lease_owner, lease_expires_at, not_before FROM jobs"
            ).fetchall(),
        }
    finally:
        conn.close()


def restore_seeded_work(home: str, snapshot: dict) -> None:
    """Undo anything the worker managed before the lease was renewed, so the seed is what shows."""

    conn = sqlite3.connect(str(db_path_for_home(home)), timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        with conn:
            conn.execute("DELETE FROM activity_events WHERE id > ?", (snapshot["activity_max_id"],))
            conn.executemany(
                "UPDATE files SET status = ?, status_reason = ?, failure_attempts = ?, failure_class = ?, "
                "last_attempt_at = ?, next_retry_at = ? WHERE id = ?",
                [(row[1], row[2], row[3], row[4], row[5], row[6], row[0]) for row in snapshot["files"]],
            )
            conn.executemany(
                "UPDATE jobs SET status = ?, last_error = ?, attempt_count = ?, lease_owner = ?, "
                "lease_expires_at = ?, not_before = ? WHERE id = ?",
                [(row[1], row[2], row[3], row[4], row[5], row[6], row[0]) for row in snapshot["jobs"]],
            )
            conn.execute("DELETE FROM jobs WHERE id > ?", (max((row[0] for row in snapshot["jobs"]), default=0),))
    finally:
        conn.close()


def seed_one_processing_record(home: str) -> None:
    """One `file_logs` row for the harness's already-seeded processed file.

    The harness seeds files, jobs, library rows and activity, but no processing records, so the
    record panel would open empty. The payload below carries the keys ``RemuxPassRunner`` sets on a
    successful live remux (``live_output_written``) — including
    ``processing_watched_folder_resolved``, which migration 0009 renamed from the Refiner-era
    spelling still baked into the screenshot this replaces.
    """

    watched = r"D:\Media\Incoming\Movies"
    output_folder = r"D:\Media\Library\Movies"
    leaf = "Late Autumn Reprise (2023)\\Late Autumn Reprise.mkv"
    detail = {
        "ok": True,
        "outcome": "live_output_written",
        "relative_media_path": RECORD_FILE,
        "inspected_source_path": f"{watched}\\{leaf}",
        "processing_watched_folder_resolved": watched,
        "processing_output_folder_resolved": output_folder,
        "media_scope": "movie",
        "plan_summary": "video copy indices: [0] | audio out: #1 eng DTS-HD 5.1 | subtitles out: eng SDH",
        "preflight_status": "ok",
        "preflight_reason": "ffprobe completed and remux plan was evaluated",
        "preflight_probe_settings": {"probe_size_mb": 10, "analyze_duration_seconds": 10},
        "stream_counts": {"video": 1, "audio": 2, "subtitle": 1},
        "audio_before": "eng DTS-HD 5.1, jpn AC3 2.0",
        "audio_after": "eng DTS-HD 5.1",
        "subs_before": "eng SDH",
        "subs_after": "eng SDH",
        "removed_audio": ["jpn AC3 2.0"],
        "removed_subtitles": [],
        "removed_images": [],
        "remux_required": True,
        "output_file": f"{output_folder}\\{leaf}",
        "output_replaced_existing": False,
        "output_collision_policy": "replace",
        "output_collision_action": "wrote",
        "output_completeness_check": "passed",
        "source_size_bytes": 6_100_000_000,
        "output_size_bytes": 5_870_000_000,
        "duration_seconds": 214.0,
        "hardware_method": None,
        "hardware_fell_back_to_software": False,
        "after_track_lines_meaning": (
            "Live remux finished; before = source probe; after = planned disposition (copy remux — "
            "ffprobe of the written file was used for validation only)."
        ),
    }
    conn = sqlite3.connect(str(db_path_for_home(home)), timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        with conn:
            row = conn.execute(
                "SELECT f.id, l.id, l.name FROM files f LEFT JOIN libraries l ON l.id = f.library_id "
                "WHERE f.relative_path = ? ORDER BY f.id LIMIT 1",
                (RECORD_FILE,),
            ).fetchone()
            if row is None:
                harness.fail(f"The harness did not seed {RECORD_FILE}; the record capture has nothing to open.")
            conn.execute(
                "INSERT INTO file_logs (file_id, library_id, relative_path, library_name, outcome, title, "
                "detail_json, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now', '-38 minutes'))",
                (
                    row[0],
                    row[1],
                    RECORD_FILE,
                    row[2] or "",
                    "live_output_written",
                    "Late Autumn Reprise.mkv was processed successfully",
                    json.dumps(detail),
                ),
            )
    finally:
        conn.close()


def capture_processing_record(browser: Browser, base_url: str, storage_state: dict, output_dir: Path) -> None:
    """Processing -> Files, with one file's processing record open.

    The harness only opens a screen's default state, and this panel is behind a button.
    """

    path = "/processing?tab=files"
    ctx = new_context(browser, theme="dark", viewport=DESKTOP_VIEWPORT, storage_state=storage_state)
    page = ctx.new_page()
    try:
        page.goto(base_url + path, wait_until="domcontentloaded")
        settle(page, READY_SELECTORS[path])
        row = page.locator('li[data-testid^="processing-file-"]', has_text="Late Autumn Reprise").first
        row.wait_for(state="visible", timeout=harness.TIMEOUT_MS)
        file_id = row.get_attribute("data-testid").rsplit("-", 1)[-1]
        page.click(f'[data-testid="processing-file-log-{file_id}"]')
        panel = page.locator('[data-testid="processing-file-log-panel"]')
        panel.wait_for(state="visible", timeout=harness.TIMEOUT_MS)
        if panel.get_by_text("0 record(s)").count():
            harness.fail("The processing record panel opened with no records in it.")
        panel.scroll_into_view_if_needed()
        page.wait_for_timeout(400)
        refuse_a_broken_frame(page, "processing-detail.png")
        page.screenshot(path=str(output_dir / "processing-detail.png"))
        print("  processing-detail.png")
    finally:
        ctx.close()


def run(browser: Browser, output_dir: Path) -> None:
    session_secret = secrets.token_hex(32)
    server, home, base_url = harness.start_weir_server(session_secret)
    username = "readme-shots"
    password = secrets.token_urlsafe(24)  # generated, never typed into the login form
    try:
        boot_ctx = browser.new_context(viewport=DESKTOP_VIEWPORT)
        boot_page = boot_ctx.new_page()
        boot_page.goto(base_url + "/", wait_until="domcontentloaded")
        harness.api_bootstrap(boot_page, username, password)
        harness.api_login(boot_page, username, password)
        storage_state = boot_ctx.storage_state()
        boot_ctx.close()

        harness.set_wizard_state(home, "skipped")
        harness.seed_representative_data(home)
        snapshot = quiesce_seeded_work(home)
        seed_one_processing_record(home)
        # Let any tick already in flight finish, then put back what it changed.
        time.sleep(5)
        restore_seeded_work(home, snapshot)

        for name, path, theme, viewport in readme_shots():
            ctx = new_context(browser, theme=theme, viewport=viewport, storage_state=storage_state)
            page = ctx.new_page()
            page.goto(base_url + path, wait_until="domcontentloaded")
            settle(page, READY_SELECTORS[path])
            refuse_a_broken_frame(page, name)
            page.screenshot(path=str(output_dir / name))
            print(f"  {name}")
            ctx.close()

        capture_processing_record(browser, base_url, storage_state, output_dir)
    finally:
        harness.runtime.stop_server(server)
        shutil.rmtree(home, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("output_dir", type=Path, help="Directory to write the README's PNGs into")
    args = parser.parse_args()

    harness.check_prerequisites()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    stopped = harness.runtime.reap_leftovers()
    if stopped:
        print(f"Stopped servers left behind by an earlier run: {', '.join(stopped)}")

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--force-color-profile=srgb"])
        try:
            run(browser, args.output_dir)
        finally:
            browser.close()
    print(f"\nWritten to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
