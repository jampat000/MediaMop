"""Visual regression smoke tests for high-risk pages.

Run with WEIR_E2E=1. Screenshots are saved to artifacts/screenshots/ for
visual inspection. The artifacts/ directory is .gitignored so no pixel-exact
baselines are committed; these are informational smoke checks. What is asserted is
the structure of each screen, rebaselined for the 3.0 screens in #462: In hand at
"/" (the dashboard folded into it in #459) and the Activity page's history statement.

Usage:
    WEIR_E2E=1 pytest tests/e2e/weir/test_visual_smoke_audit.py -v

To capture fresh screenshots (e.g. after intentional UI changes):
    WEIR_E2E=1 pytest tests/e2e/weir/test_visual_smoke_audit.py -v
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
    pytest.mark.weir_e2e,
    pytest.mark.skipif(
        os.environ.get("WEIR_E2E") != "1",
        reason="Weir E2E requires WEIR_E2E=1 (see tests/e2e/weir/conftest.py).",
    ),
]

# Directory where screenshots are persisted (informational, .gitignored).
_SCREENSHOT_DIR = Path(__file__).resolve().parents[3] / "artifacts" / "screenshots"


def _save_screenshot(page, test_name: str) -> None:
    """Save a viewport-only screenshot to artifacts/screenshots/<test_name>.png."""
    _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = _SCREENSHOT_DIR / f"{test_name}.png"
    page.screenshot(path=str(path), full_page=False)


def _scroll_to_top(page) -> None:
    """Reset the document immediately, even when smooth scrolling is enabled."""
    page.evaluate(
        """() => {
            const root = document.documentElement;
            const previous = root.style.scrollBehavior;
            root.style.scrollBehavior = 'auto';
            window.scrollTo(0, 0);
            root.style.scrollBehavior = previous;
        }"""
    )
    page.wait_for_function("window.scrollY === 0")


def _assert_no_error_state(page) -> None:
    """Assert no error-boundary overlay or generic crash message is visible."""
    expect(page.get_by_test_id("error-boundary")).not_to_be_visible(timeout=2_000)
    expect(page.get_by_text("Something went wrong", exact=False)).not_to_be_visible(
        timeout=2_000
    )


def _assert_document_owns_vertical_scroll(page) -> None:
    """Signed-in pages must not trap wheel input inside the main shell."""
    scroll = page.evaluate(
        """() => {
            const main = document.querySelector('.mm-main');
            const layout = document.querySelector('.mm-app-layout');
            return {
                mainOverflowY: getComputedStyle(main).overflowY,
                layoutOverflowY: getComputedStyle(layout).overflowY,
                scrollingElement: document.scrollingElement?.tagName,
            };
        }"""
    )
    assert scroll["mainOverflowY"] not in {"auto", "scroll"}, scroll
    assert scroll["layoutOverflowY"] not in {"auto", "scroll"}, scroll
    assert scroll["scrollingElement"] == "HTML", scroll


def _assert_tab_workspace(page, *, page_test_id: str, tabs_test_id: str) -> None:
    """A page uses the shared themed tab bar and accessible panel contract."""
    workspace = page.get_by_test_id(page_test_id)
    expect(workspace).to_have_class(re.compile(r"\bmm-workspace-page\b"))
    tabs = page.get_by_test_id(tabs_test_id)
    expect(tabs).to_have_class(re.compile(r"\bmm-workspace-tabs\b"))
    active_tab = tabs.locator("[role='tab'][aria-selected='true']")
    expect(active_tab).to_have_count(1)
    panel_id = active_tab.get_attribute("aria-controls")
    assert panel_id, "active workspace tab must identify its panel"
    panel = page.locator(f"#{panel_id}")
    expect(panel).to_be_visible()
    expect(panel).to_have_attribute("aria-labelledby", active_tab.get_attribute("id"))


def test_old_dashboard_address_is_not_found(weir_shell: str) -> None:
    """The dashboard folded into In hand (#459) and 3.0.0 dropped the redirect it left behind.

    /dashboard gets the not-found page, which offers the way to In hand rather than
    silently pretending the address is still a page.
    """
    base = weir_shell.rstrip("/")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 900})
            page.set_default_timeout(30_000)

            ensure_signed_in(page, base)

            page.goto(f"{base}/dashboard", wait_until="domcontentloaded")
            expect(page).to_have_url(re.compile(r".*/dashboard"))
            expect(
                page.get_by_role("heading", name="Page not found", exact=True)
            ).to_be_visible()
            expect(page.get_by_role("link", name="Dashboard", exact=True)).to_have_count(0)
            _assert_no_error_state(page)

            page.get_by_role("link", name="Go to In hand", exact=True).click()
            expect(page).to_have_url(re.compile(r".*/(?:$|[?#])"))
            expect(page.get_by_role("heading", name="In hand", exact=True)).to_be_visible()
        finally:
            browser.close()


def test_in_hand_is_the_landing_page(weir_shell: str) -> None:
    """3.0 lands on In hand at "/": what Weir is holding (#463)."""
    base = weir_shell.rstrip("/")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 900})
            page.set_default_timeout(30_000)

            ensure_signed_in(page, base)
            page.goto(f"{base}/", wait_until="domcontentloaded")

            expect(page.get_by_role("heading", name="In hand", exact=True)).to_be_visible()
            # Page content only: the shell brand line is replaced by the Weir rename (#458).
            expect(page.locator("main").get_by_text("your library", exact=False)).to_have_count(0)
            _assert_document_owns_vertical_scroll(page)
            _assert_no_error_state(page)
            _save_screenshot(page, "in-hand")
        finally:
            browser.close()


def test_activity_page_says_how_far_back_history_goes(weir_shell: str) -> None:
    """The 3.0 Activity page: filters, and a plain statement of its history horizon (#469)."""
    base = weir_shell.rstrip("/")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 900})
            page.set_default_timeout(30_000)

            ensure_signed_in(page, base)
            open_sidebar(page, "Activity")

            expect(page).to_have_url(re.compile(r".*/activity(?:$|[/?#])"))
            expect(page.get_by_role("heading", name="Activity", exact=True)).to_be_visible()
            expect(page.get_by_test_id("activity-retention")).to_contain_text("History goes back 90 days")
            expect(page.get_by_test_id("activity-feed")).to_be_visible()
            _assert_no_error_state(page)
            _save_screenshot(page, "activity")
        finally:
            browser.close()


def test_settings_general_tab_renders(weir_shell: str) -> None:
    """Every Settings tab keeps its desktop navigation and panel edges aligned."""
    base = weir_shell.rstrip("/")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 900})
            page.set_default_timeout(30_000)

            ensure_signed_in(page, base)

            open_sidebar(page, "Settings")
            expect(page).to_have_url(re.compile(r".*/settings"))

            expect(page.get_by_test_id("suite-settings-page")).to_be_visible()
            expect(page.get_by_test_id("suite-settings-global")).to_be_visible()

            settings_tabs = page.locator(".mm-workspace-tabs__button")
            for index in range(settings_tabs.count()):
                settings_tab = settings_tabs.nth(index)
                settings_tab.click()
                expect(settings_tab).to_have_attribute("aria-selected", "true")

            page.get_by_role("tab", name="Security", exact=True).click()
            expect(page.get_by_test_id("suite-settings-security")).to_be_visible()
            _scroll_to_top(page)
            page.screenshot(
                path=str(_SCREENSHOT_DIR / "settings-security-full.png"),
                full_page=True,
            )

            page.get_by_role("tab", name="General", exact=True).click()
            expect(page.get_by_test_id("suite-settings-global")).to_be_visible()

            _assert_document_owns_vertical_scroll(page)
            _assert_no_error_state(page)
            _scroll_to_top(page)
            _save_screenshot(page, "settings-general")
            page.screenshot(
                path=str(_SCREENSHOT_DIR / "settings-general-full.png"),
                full_page=True,
            )
        finally:
            browser.close()


def test_module_sections_share_themed_tabs_and_responsive_layout(
    weir_shell: str,
) -> None:
    """Processing uses the shared horizontal tab bar without page overflow."""
    base = weir_shell.rstrip("/")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(viewport={"width": 1600, "height": 900})
            page = context.new_page()
            page.set_default_timeout(30_000)
            ensure_signed_in(page, base)

            for label, page_test_id, tabs_test_id, screenshot_name in (
                (
                    "Processing",
                    "processing-scope-page",
                    "processing-section-tabs",
                    "processing-workspace",
                ),
            ):
                open_sidebar(page, label)
                _assert_tab_workspace(
                    page,
                    page_test_id=page_test_id,
                    tabs_test_id=tabs_test_id,
                )
                _assert_document_owns_vertical_scroll(page)
                _assert_no_error_state(page)
                _scroll_to_top(page)
                _save_screenshot(page, screenshot_name)

                mobile_page = context.new_page()
                try:
                    mobile_page.set_viewport_size({"width": 390, "height": 844})
                    mobile_page.set_default_timeout(30_000)
                    mobile_page.goto(page.url, wait_until="domcontentloaded")
                    _assert_tab_workspace(
                        mobile_page,
                        page_test_id=page_test_id,
                        tabs_test_id=tabs_test_id,
                    )
                    assert mobile_page.evaluate(
                        "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
                    ), f"{label} workspace overflows the narrow viewport"
                    _assert_document_owns_vertical_scroll(mobile_page)
                    _assert_no_error_state(mobile_page)
                    _save_screenshot(mobile_page, f"{screenshot_name}-mobile")
                finally:
                    mobile_page.close()
        finally:
            browser.close()


def test_processing_audio_subtitles_editor_renders(weir_shell: str) -> None:
    """The full audio & subtitle profile editor remains readable at desktop width."""
    base = weir_shell.rstrip("/")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 900})
            page.set_default_timeout(30_000)
            ensure_signed_in(page, base)

            open_sidebar(page, "Processing")
            page.get_by_role("tab", name="Audio & subtitles", exact=True).click()
            expect(page.get_by_test_id("processing-rule-set-workspace")).to_be_visible()
            page.get_by_role("button", name="New profile →", exact=True).click()
            expect(page.get_by_label("Profile name", exact=True)).to_be_visible()
            expect(page.get_by_text("Audio order", exact=True)).not_to_be_visible()

            _assert_document_owns_vertical_scroll(page)
            _assert_no_error_state(page)
            _scroll_to_top(page)
            _save_screenshot(page, "processing-audio-subtitles")
            page.screenshot(
                path=str(_SCREENSHOT_DIR / "processing-audio-subtitles-full.png"),
                full_page=True,
            )
            page.set_viewport_size({"width": 390, "height": 844})
            _scroll_to_top(page)
            page.wait_for_timeout(300)
            _save_screenshot(page, "processing-audio-subtitles-mobile")
        finally:
            browser.close()
