from __future__ import annotations

import os
import re

import pytest
from playwright.sync_api import expect, sync_playwright

from ._helpers import ensure_signed_in, open_sidebar

pytestmark = [
    pytest.mark.mediamop_e2e,
    pytest.mark.skipif(
        os.environ.get("MEDIAMOP_E2E") != "1",
        reason="MediaMop E2E requires MEDIAMOP_E2E=1 (see tests/e2e/mediamop/conftest.py).",
    ),
]


def test_signed_in_navigation_covers_main_screens_and_tabs(mediamop_shell: str) -> None:
    base = mediamop_shell.rstrip("/")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_default_timeout(30_000)

            ensure_signed_in(page, base)

            open_sidebar(page, "Dashboard")
            expect(page).to_have_url(re.compile(r".*/app(?:$|[/?#])"))
            expect(page.get_by_test_id("dashboard-page")).to_be_visible()
            expect(page.get_by_test_id("dashboard-status-strip")).to_be_visible()
            expect(page.get_by_test_id("dashboard-module-cards")).to_be_visible()
            expect(page.get_by_test_id("dashboard-global-jobs")).to_be_visible()
            expect(page.get_by_test_id("dashboard-runtime-health")).not_to_be_visible()

            open_sidebar(page, "Activity")
            expect(page).to_have_url(re.compile(r".*/app/activity"))
            expect(page.get_by_test_id("activity-feed")).to_be_visible()
            expect(page.get_by_text("Showing now", exact=False)).to_be_visible()
            expect(page.get_by_text("Matches in store", exact=False)).to_be_visible()
            expect(page.locator("select").nth(0)).to_contain_text("All modules")
            expect(page.locator("select").nth(0)).to_contain_text("System")

            open_sidebar(page, "Refiner")
            expect(page).to_have_url(re.compile(r".*/app/refiner"))
            expect(page.get_by_test_id("refiner-scope-page")).to_be_visible()
            page.get_by_role("tab", name="Libraries", exact=True).click()
            expect(page.get_by_test_id("refiner-path-settings")).to_be_visible()
            page.get_by_role("tab", name="Audio & subtitles", exact=True).click()
            expect(page.get_by_test_id("refiner-remux-section")).to_be_visible()
            page.get_by_role("tab", name="Schedules", exact=True).click()
            expect(page.get_by_test_id("refiner-schedules-section")).to_be_visible()
            page.get_by_role("tab", name="Jobs", exact=True).click()
            expect(page.get_by_test_id("refiner-jobs-inspection-section")).to_be_visible()
            page.get_by_role("tab", name="Overview", exact=True).click()
            expect(page.get_by_test_id("refiner-overview-panel")).to_be_visible()

            open_sidebar(page, "Pruner")
            expect(page).to_have_url(re.compile(r".*/app/pruner"))
            expect(page.get_by_test_id("pruner-top-level-tabs")).to_be_visible()
            expect(page.get_by_test_id("pruner-top-overview-tab")).to_be_visible()
            page.get_by_role("tab", name="Emby", exact=True).click()
            expect(page.get_by_test_id("pruner-provider-tab-emby")).to_be_visible()
            expect(page.get_by_test_id("pruner-connection-panel-emby")).to_be_visible()
            page.get_by_role("tab", name="Jellyfin", exact=True).click()
            expect(page.get_by_test_id("pruner-provider-tab-jellyfin")).to_be_visible()
            expect(page.get_by_test_id("pruner-connection-panel-jellyfin")).to_be_visible()
            page.get_by_role("tab", name="Plex", exact=True).click()
            expect(page.get_by_test_id("pruner-provider-tab-plex")).to_be_visible()
            expect(page.get_by_test_id("pruner-connection-panel-plex")).to_be_visible()
            page.get_by_role("tab", name="Jobs", exact=True).click()
            expect(page.get_by_test_id("pruner-top-jobs-tab")).to_be_visible()

            open_sidebar(page, "Subber")
            expect(page).to_have_url(re.compile(r".*/app/subber"))
            expect(page.get_by_test_id("subber-scope-page")).to_be_visible()
            expect(page.get_by_test_id("subber-overview-tab")).to_be_visible()
            page.get_by_role("tab", name="TV", exact=True).click()
            expect(page.get_by_test_id("subber-tv-tab")).to_be_visible()
            page.get_by_role("tab", name="Movies", exact=True).click()
            expect(page.get_by_test_id("subber-movies-tab")).to_be_visible()
            page.get_by_role("tab", name="Connections", exact=True).click()
            expect(page.get_by_test_id("subber-connections-tab")).to_be_visible()
            page.get_by_role("tab", name="Providers", exact=True).click()
            expect(page.get_by_test_id("subber-providers-tab")).to_be_visible()
            page.get_by_role("tab", name="Preferences", exact=True).click()
            expect(page.get_by_test_id("subber-preferences-tab")).to_be_visible()
            page.get_by_role("tab", name="Schedule", exact=True).click()
            expect(page.get_by_test_id("subber-schedule-tab")).to_be_visible()
            page.get_by_role("tab", name="Jobs", exact=True).click()
            expect(page.get_by_test_id("subber-jobs-tab")).to_be_visible()

            open_sidebar(page, "Settings")
            expect(page).to_have_url(re.compile(r".*/app/settings"))
            expect(page.get_by_test_id("suite-settings-page")).to_be_visible()
            expect(page.get_by_test_id("suite-settings-global")).to_be_visible()
            expect(page.get_by_text("Setup wizard", exact=True)).to_be_visible()
            expect(page.get_by_text("Timezone", exact=True)).to_be_visible()
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
