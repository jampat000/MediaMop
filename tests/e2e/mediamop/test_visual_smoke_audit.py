"""Visual regression smoke tests for high-risk pages.

Run with MEDIAMOP_E2E=1. Screenshots are saved to artifacts/screenshots/ for
visual inspection. The artifacts/ directory is .gitignored so no pixel-exact
baselines are committed; these are informational smoke checks.

Usage:
    MEDIAMOP_E2E=1 pytest tests/e2e/mediamop/test_visual_smoke_audit.py -v

To capture fresh screenshots (e.g. after intentional UI changes):
    MEDIAMOP_E2E=1 pytest tests/e2e/mediamop/test_visual_smoke_audit.py -v
    (screenshots are always overwritten on each run)
"""
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

# Directory where screenshots are persisted (informational, .gitignored).
_SCREENSHOT_DIR = Path(__file__).resolve().parents[3] / "artifacts" / "screenshots"


def _save_screenshot(page, test_name: str) -> None:
    """Save a viewport-only screenshot to artifacts/screenshots/<test_name>.png."""
    _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = _SCREENSHOT_DIR / f"{test_name}.png"
    page.screenshot(path=str(path), full_page=False)


def _assert_no_error_state(page) -> None:
    """Assert no error-boundary overlay or generic crash message is visible."""
    expect(page.get_by_test_id("error-boundary")).not_to_be_visible(timeout=2_000)
    expect(page.get_by_text("Something went wrong", exact=False)).not_to_be_visible(
        timeout=2_000
    )


def test_dashboard_renders_without_error(mediamop_shell: str) -> None:
    """Dashboard page loads, shows key structural elements, and is error-free."""
    base = mediamop_shell.rstrip("/")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_default_timeout(30_000)

            ensure_signed_in(page, base)

            open_sidebar(page, "Dashboard")
            expect(page).to_have_url(re.compile(r".*/(?:$|[/?#])"))

            expect(page.get_by_test_id("dashboard-page")).to_be_visible()
            expect(page.get_by_test_id("dashboard-status-strip")).to_be_visible()
            expect(page.get_by_test_id("dashboard-module-cards")).to_be_visible()

            _assert_no_error_state(page)
            _save_screenshot(page, "dashboard")
        finally:
            browser.close()


def test_settings_general_tab_renders(mediamop_shell: str) -> None:
    """Settings page (General tab) loads, shows global settings panel, and is error-free."""
    base = mediamop_shell.rstrip("/")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_default_timeout(30_000)

            ensure_signed_in(page, base)

            open_sidebar(page, "Settings")
            expect(page).to_have_url(re.compile(r".*/settings"))

            expect(page.get_by_test_id("suite-settings-page")).to_be_visible()
            expect(page.get_by_test_id("suite-settings-global")).to_be_visible()

            _assert_no_error_state(page)
            _save_screenshot(page, "settings-general")
        finally:
            browser.close()


def test_subber_providers_tab_renders(mediamop_shell: str) -> None:
    """Subber page Providers tab loads and is error-free."""
    base = mediamop_shell.rstrip("/")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_default_timeout(30_000)

            ensure_signed_in(page, base)

            open_sidebar(page, "Subber")
            expect(page).to_have_url(re.compile(r".*/subber"))
            expect(page.get_by_test_id("subber-scope-page")).to_be_visible()

            page.get_by_role("tab", name="Providers", exact=True).click()
            expect(page.get_by_test_id("subber-providers-tab")).to_be_visible()

            _assert_no_error_state(page)
            _save_screenshot(page, "subber-providers")
        finally:
            browser.close()
