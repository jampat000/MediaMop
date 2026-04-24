"""Playwright smoke: bootstrap -> login -> setup wizard -> app -> logout -> guard redirect."""

from __future__ import annotations

import os
import re

import pytest
from playwright.sync_api import expect, sync_playwright

pytestmark = [
    pytest.mark.mediamop_e2e,
    pytest.mark.skipif(
        os.environ.get("MEDIAMOP_E2E") != "1",
        reason="MediaMop E2E requires MEDIAMOP_E2E=1 (see tests/e2e/mediamop/conftest.py).",
    ),
]

BOOTSTRAP_USER = "e2e-shell-admin"
BOOTSTRAP_PASS = "e2e-shell-pass-min8"
_URL_ASSERT_MS = 20_000


def test_auth_shell_bootstrap_login_logout_guard(mediamop_shell: str) -> None:
    base = mediamop_shell.rstrip("/")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_default_timeout(30_000)

            page.goto(f"{base}/", wait_until="domcontentloaded")
            expect(page).to_have_url(re.compile(r".*/setup"))

            page.get_by_test_id("setup-username").fill(BOOTSTRAP_USER)
            page.get_by_test_id("setup-password").fill(BOOTSTRAP_PASS)
            page.get_by_test_id("setup-submit").click()

            expect(page).to_have_url(re.compile(r".*/login"))
            expect(page.get_by_text("Initial account created", exact=False)).to_be_visible()

            page.get_by_test_id("login-username").fill(BOOTSTRAP_USER)
            page.get_by_test_id("login-password").fill(BOOTSTRAP_PASS)
            page.get_by_test_id("login-submit").click()

            expect(page).to_have_url(re.compile(r".*/app/setup-wizard"))
            expect(page.get_by_text("Setup wizard", exact=False)).to_be_visible()
            page.get_by_test_id("setup-wizard-skip").click()

            expect(page).to_have_url(re.compile(r".*/app"))
            expect(page.get_by_test_id("shell-ready")).to_be_visible()

            with page.expect_response(
                lambda response: response.url.endswith("/api/v1/auth/logout"),
                timeout=_URL_ASSERT_MS,
            ) as logout_response:
                page.get_by_test_id("sign-out").click()
            assert logout_response.value.ok
            expect(page).to_have_url(re.compile(r".*/login"), timeout=_URL_ASSERT_MS)

            page.goto(f"{base}/app", wait_until="domcontentloaded")
            expect(page).to_have_url(re.compile(r".*/login"), timeout=_URL_ASSERT_MS)
        finally:
            browser.close()
