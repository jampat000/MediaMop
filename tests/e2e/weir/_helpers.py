from __future__ import annotations

import contextlib
import re
import time

from playwright.sync_api import Page, expect
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

BOOTSTRAP_USER = "e2e-shell-admin"
BOOTSTRAP_PASS = "e2e-shell-pass-min8"
URL_ASSERT_MS = 20_000
# Creating the admin and signing in both hash a password (Argon2id), which takes the server about half a
# second. Clicking again while the first request is still pending hits a disabled button that then
# detaches when the page navigates, so each submit waits for its page to be left before looking again.
SUBMIT_SETTLE_MS = 15_000


def _left_page(path: str):
    pattern = re.compile(rf"{re.escape(path)}(?:$|[?#])")
    return lambda url: pattern.search(url) is None


def ensure_signed_in(page: Page, base_url: str) -> None:
    base = base_url.rstrip("/")
    page.goto(f"{base}/", wait_until="domcontentloaded")
    deadline = time.time() + (URL_ASSERT_MS / 1000)
    while time.time() < deadline:
        page.wait_for_load_state("domcontentloaded")

        if page.get_by_test_id("setup-username").count() > 0:
            page.get_by_test_id("setup-username").fill(BOOTSTRAP_USER)
            page.get_by_test_id("setup-password").fill(BOOTSTRAP_PASS)
            page.get_by_test_id("setup-submit").click()
            with contextlib.suppress(PlaywrightTimeoutError):
                page.wait_for_url(_left_page("/setup"), timeout=SUBMIT_SETTLE_MS)
            continue

        if page.get_by_test_id("login-username").count() > 0:
            page.get_by_test_id("login-username").fill(BOOTSTRAP_USER)
            page.get_by_test_id("login-password").fill(BOOTSTRAP_PASS)
            page.get_by_test_id("login-submit").click()
            with contextlib.suppress(PlaywrightTimeoutError):
                page.wait_for_url(_left_page("/login"), timeout=SUBMIT_SETTLE_MS)
            continue

        if page.get_by_test_id("shell-ready").count() > 0:
            expect(page.get_by_test_id("shell-ready")).to_be_visible(timeout=2_000)
            return

        if "/setup-wizard" in page.url and page.get_by_test_id("setup-wizard-skip").count() > 0:
            expect(page.get_by_role("heading", name="Set up Weir")).to_be_visible()
            page.get_by_test_id("setup-wizard-skip").click()
            # Wait for navigation away from setup-wizard.  The skip handler batches
            # multiple mutations (suite + refiner) that can take 1-3 s when
            # settings from a prior test run persist in the DB.  A fixed 500 ms sleep
            # is not enough — the loop would re-click skip before navigation completes,
            # stacking overlapping saves and eventually timing out.
            try:
                page.wait_for_url(
                    lambda url: "/setup-wizard" not in url, timeout=10_000
                )
            except Exception:
                pass
            continue

        if re.search(r"/(?:$|[?#])", page.url) or "/login" in page.url or "/setup" in page.url:
            page.wait_for_timeout(500)
            continue

        page.goto(f"{base}/", wait_until="domcontentloaded")

    expect(page.get_by_test_id("shell-ready")).to_be_visible(timeout=URL_ASSERT_MS)


def open_sidebar(page: Page, label: str) -> None:
    page.get_by_role("link", name=label, exact=True).click()
