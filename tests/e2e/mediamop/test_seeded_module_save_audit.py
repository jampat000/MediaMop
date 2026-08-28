from __future__ import annotations

import os
import re
from pathlib import Path

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


def test_saved_state_persists_across_settings_refiner_and_pruner(
    mediamop_shell: str,
    mediamop_home: str,
) -> None:
    base = mediamop_shell.rstrip("/")
    tv_watch = Path(mediamop_home) / "e2e" / "tv-watch-missing"
    tv_output = Path(mediamop_home) / "e2e" / "tv-output"
    tv_output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_default_timeout(30_000)

            ensure_signed_in(page, base)

            open_sidebar(page, "Settings")
            expect(page.get_by_test_id("suite-settings-global")).to_be_visible()
            page.get_by_test_id("suite-settings-open-setup-wizard").click()
            expect(page).to_have_url(re.compile(r".*/setup-wizard"))
            page.get_by_label("Display density").get_by_text("Comfortable").click()
            page.get_by_test_id("setup-wizard-skip").click()
            expect(page).to_have_url(re.compile(r".*/(?:$|[/?#])"))
            expect(page.locator("html")).to_have_attribute("data-mm-density", "comfortable")

            open_sidebar(page, "Refiner")
            page.get_by_role("tab", name="Libraries", exact=True).click()
            libraries = page.get_by_test_id("refiner-libraries-section")
            expect(libraries).to_be_visible()
            libraries.get_by_role("button", name="Edit").nth(1).click()
            form = page.get_by_test_id("refiner-library-form")
            form.get_by_role("textbox", name="Watched folder").fill(str(tv_watch))
            form.get_by_role("textbox", name="Output folder").fill(str(tv_output))
            page.get_by_test_id("refiner-library-save").click()
            open_sidebar(page, "Dashboard")
            open_sidebar(page, "Refiner")
            page.get_by_role("tab", name="Libraries", exact=True).click()
            expect(page.get_by_test_id("refiner-libraries-section")).to_contain_text(str(tv_watch))

            open_sidebar(page, "Pruner")
            page.get_by_role("tab", name="Emby", exact=True).click()
            emby_panel = page.get_by_test_id("pruner-connection-panel-emby")
            emby_panel.get_by_label("Base URL", exact=True).fill("http://emby.test:8096")
            emby_panel.get_by_placeholder("Enter API key", exact=True).fill("emby-token")
            emby_panel.get_by_role("button", name="Save Emby", exact=True).click()
            expect(page.get_by_test_id("pruner-connection-status-emby")).to_contain_text(
                "Not tested yet",
            )
            open_sidebar(page, "Dashboard")
            open_sidebar(page, "Pruner")
            page.get_by_role("tab", name="Emby", exact=True).click()
            expect(page.get_by_test_id("pruner-connection-panel-emby").get_by_label("Base URL", exact=True)).to_have_value(
                "http://emby.test:8096",
            )

        finally:
            browser.close()
