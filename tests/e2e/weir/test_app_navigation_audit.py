from __future__ import annotations

import os
import re

import pytest
from playwright.sync_api import expect, sync_playwright

from ._helpers import ensure_signed_in, open_sidebar

pytestmark = [
    pytest.mark.weir_e2e,
    pytest.mark.skipif(
        os.environ.get("WEIR_E2E") != "1",
        reason="Weir E2E requires WEIR_E2E=1 (see tests/e2e/weir/conftest.py).",
    ),
]


def test_signed_in_navigation_covers_main_screens_and_tabs(weir_shell: str) -> None:
    base = weir_shell.rstrip("/")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_default_timeout(30_000)

            ensure_signed_in(page, base)

            open_sidebar(page, "Home")
            expect(page).to_have_url(re.compile(r".*/(?:$|[/?#])"))
            expect(page.get_by_role("heading", name="Home", exact=True)).to_be_visible()
            # The dashboard folded into Home (#459) and 3.0.0 dropped its redirect: no
            # sidebar entry, and /dashboard is the not-found page rather than a hidden alias.
            expect(page.get_by_role("link", name="Dashboard", exact=True)).to_have_count(0)
            page.goto(f"{base}/dashboard", wait_until="domcontentloaded")
            expect(
                page.get_by_role("heading", name="Page not found", exact=True)
            ).to_be_visible()
            page.goto(base + "/", wait_until="domcontentloaded")
            expect(page.get_by_role("heading", name="Home", exact=True)).to_be_visible()

            open_sidebar(page, "Activity")
            expect(page).to_have_url(re.compile(r".*/activity"))
            expect(page.get_by_test_id("activity-feed")).to_be_visible()
            expect(page.get_by_test_id("activity-summary")).to_contain_text("Showing")
            # Weir is one app: no Module filter.
            expect(page.get_by_text("All modules", exact=True)).to_have_count(0)

            open_sidebar(page, "Processing")
            expect(page).to_have_url(re.compile(r".*/processing"))
            expect(page.get_by_test_id("processing-scope-page")).to_be_visible()
            page.get_by_role("tab", name="Libraries", exact=True).click()
            expect(page.get_by_test_id("processing-libraries-section")).to_be_visible()
            page.get_by_role("tab", name="Audio & subtitles", exact=True).click()
            expect(page.get_by_test_id("processing-rule-set-workspace")).to_be_visible()
            page.get_by_role("tab", name="Schedules", exact=True).click()
            expect(page.get_by_test_id("processing-schedules-section")).to_be_visible()
            page.get_by_role("tab", name="Jobs", exact=True).click()
            expect(page.get_by_test_id("processing-jobs-inspection-section")).to_be_visible()
            page.get_by_role("tab", name="Overview", exact=True).click()
            expect(page.get_by_test_id("processing-overview-panel")).to_be_visible()
            # Old /processing links still land on the same tab.
            page.goto(f"{base}/processing?tab=jobs", wait_until="domcontentloaded")
            expect(page).to_have_url(re.compile(r".*/processing\?tab=jobs"))
            expect(page.get_by_test_id("processing-jobs-inspection-section")).to_be_visible()


            open_sidebar(page, "Settings")
            expect(page).to_have_url(re.compile(r".*/settings"))
            expect(page.get_by_test_id("suite-settings-page")).to_be_visible()
            expect(page.get_by_test_id("suite-settings-global")).to_be_visible()
            expect(page.get_by_text("Setup wizard", exact=True)).to_be_visible()
            expect(page.get_by_text("Time zone", exact=True)).to_be_visible()
            expect(page.get_by_text("Display density", exact=False)).to_be_visible()
            expect(page.get_by_text("Upgrade", exact=True)).to_be_visible()
            page.get_by_role("tab", name="Security", exact=True).click()
            expect(page.get_by_test_id("suite-settings-security")).to_be_visible()
            expect(page.get_by_role("heading", name="Change password", exact=True)).to_be_visible()
            page.get_by_role("tab", name="Logs", exact=True).click()
            expect(page.get_by_test_id("suite-settings-logs")).to_be_visible()
            expect(page.get_by_text("Showing now", exact=False)).to_be_visible()
            expect(page.get_by_text("Matching events", exact=False)).to_be_visible()
            expect(page.get_by_text("Server diagnostics", exact=True)).to_be_visible()
            expect(page.get_by_text("System events", exact=True)).to_be_visible()
        finally:
            browser.close()
