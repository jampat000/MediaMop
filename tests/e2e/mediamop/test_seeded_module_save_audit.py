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


def test_saved_state_persists_across_settings_refiner_pruner_and_subber(
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
            expect(page).to_have_url(re.compile(r".*/app/setup-wizard"))
            page.get_by_label("Display density").get_by_text("Comfortable").click()
            page.get_by_test_id("setup-wizard-skip").click()
            expect(page).to_have_url(re.compile(r".*/app(?:$|[/?#])"))
            expect(page.locator("html")).to_have_attribute("data-mm-density", "comfortable")

            open_sidebar(page, "Refiner")
            page.get_by_role("tab", name="Libraries", exact=True).click()
            refiner_paths = page.get_by_test_id("refiner-path-settings")
            tv_card = refiner_paths.locator(".mm-dash-grid > .mm-card").nth(0)
            tv_inputs = tv_card.locator("input")
            tv_watched = tv_inputs.nth(0)
            tv_output_input = tv_inputs.nth(2)
            tv_watched.fill(str(tv_watch))
            tv_output_input.fill(str(tv_output))
            tv_card.get_by_role("button", name="Save TV path settings", exact=True).click()
            expect(page.get_by_test_id("refiner-path-settings-saved-hint")).to_be_visible()
            open_sidebar(page, "Dashboard")
            open_sidebar(page, "Refiner")
            page.get_by_role("tab", name="Libraries", exact=True).click()
            restored_tv_card = page.get_by_test_id("refiner-path-settings").locator(".mm-dash-grid > .mm-card").nth(0)
            restored_tv_inputs = restored_tv_card.locator("input")
            expect(restored_tv_inputs.nth(0)).to_have_value(str(tv_watch))
            expect(restored_tv_inputs.nth(2)).to_have_value(str(tv_output))

            open_sidebar(page, "Pruner")
            page.get_by_role("tab", name="Emby", exact=True).click()
            emby_panel = page.get_by_test_id("pruner-connection-panel-emby")
            emby_panel.get_by_label("Base URL", exact=True).fill("http://emby.test:8096")
            emby_panel.get_by_label("API key", exact=True).fill("emby-token")
            emby_panel.get_by_role("button", name="Save Emby", exact=True).click()
            expect(page.get_by_test_id("pruner-connection-save-ok-emby")).to_be_visible()
            open_sidebar(page, "Dashboard")
            open_sidebar(page, "Pruner")
            page.get_by_role("tab", name="Emby", exact=True).click()
            expect(page.get_by_test_id("pruner-connection-panel-emby").get_by_label("Base URL", exact=True)).to_have_value(
                "http://emby.test:8096",
            )

            open_sidebar(page, "Subber")
            page.get_by_role("tab", name="Connections", exact=True).click()
            sonarr = page.get_by_test_id("subber-settings-sonarr")
            sonarr.get_by_label("Base URL", exact=True).fill("http://sonarr.test:8989")
            sonarr.get_by_label("API key", exact=True).fill("sonarr-token")
            page.get_by_test_id("subber-save-sonarr").click()
            expect(sonarr.get_by_role("status")).to_contain_text("Saved.")
            open_sidebar(page, "Dashboard")
            open_sidebar(page, "Subber")
            page.get_by_role("tab", name="Connections", exact=True).click()
            expect(page.get_by_test_id("subber-settings-sonarr").get_by_label("Base URL", exact=True)).to_have_value(
                "http://sonarr.test:8989",
            )
        finally:
            browser.close()
