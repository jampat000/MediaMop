from __future__ import annotations

import re
import time

from playwright.sync_api import Page, expect

BOOTSTRAP_USER = "e2e-shell-admin"
BOOTSTRAP_PASS = "e2e-shell-pass-min8"
URL_ASSERT_MS = 20_000


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
            page.wait_for_timeout(500)
            continue

        if page.get_by_test_id("login-username").count() > 0:
            page.get_by_test_id("login-username").fill(BOOTSTRAP_USER)
            page.get_by_test_id("login-password").fill(BOOTSTRAP_PASS)
            page.get_by_test_id("login-submit").click()
            page.wait_for_timeout(500)
            continue

        if page.get_by_test_id("shell-ready").count() > 0:
            expect(page.get_by_test_id("shell-ready")).to_be_visible(timeout=2_000)
            return

        if "/setup-wizard" in page.url and page.get_by_test_id("setup-wizard-skip").count() > 0:
            expect(page.get_by_text("Setup wizard", exact=False)).to_be_visible()
            page.get_by_test_id("setup-wizard-skip").click()
            page.wait_for_timeout(500)
            continue

        if re.search(r"/(?:$|[?#])", page.url) or "/login" in page.url or "/setup" in page.url:
            page.wait_for_timeout(500)
            continue

        page.goto(f"{base}/", wait_until="domcontentloaded")

    expect(page.get_by_test_id("shell-ready")).to_be_visible(timeout=URL_ASSERT_MS)


def open_sidebar(page: Page, label: str) -> None:
    page.get_by_role("link", name=label, exact=True).click()
