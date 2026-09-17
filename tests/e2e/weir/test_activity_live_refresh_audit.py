from __future__ import annotations

import os

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


def test_activity_feed_updates_without_manual_refresh(
    weir_shell: str,
    seed_activity_event,
) -> None:
    marker_detail = "Live refresh reached the open Activity page."
    base = weir_shell.rstrip("/")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_default_timeout(30_000)

            ensure_signed_in(page, base)
            open_sidebar(page, "Activity")

            expect(page.get_by_text(marker_detail, exact=True)).to_have_count(0)

            seed_activity_event(
                event_type="auth.password_changed",
                module="auth",
                title="Live refresh marker event",
                detail=marker_detail,
            )

            expect(page.get_by_role("heading", name="Password changed")).to_be_visible(timeout=10_000)
            expect(page.get_by_text(marker_detail, exact=True)).to_be_visible(timeout=10_000)
            expect(page.get_by_text("Account and sign-in activity", exact=True).first).to_be_visible()
        finally:
            browser.close()
