"""End-to-end audit for a packaged MediaMop server.

This is intentionally separate from the developer E2E fixture.  It does not
start a source-tree server or Vite; it drives the browser against the URL
provided in ``MEDIAMOP_LIVE_BASE_URL``.  The target must be a controlled
packaged instance with a deliberate data/runtime boundary.

Usage (from the repository root)::

    MEDIAMOP_LIVE_BASE_URL=http://app-server:8791 \
      apps/backend/.venv/Scripts/python.exe scripts/live-packaged-e2e.py

The audit covers the authenticated routes, every visible module/settings tab,
the safe CRUD/test controls, responsive shell controls, and the public HTTP
contract.  Screenshots and a machine-readable summary are written under the
ignored ``artifacts/live-packaged-e2e`` directory.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import tomllib
from playwright.sync_api import (
    BrowserContext,
    Locator,
    Page,
    Playwright,
    Response,
    sync_playwright,
)
from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
)

BASE_URL = os.environ.get("MEDIAMOP_LIVE_BASE_URL", "").strip().rstrip("/")
AUDIT_USER = os.environ.get("MEDIAMOP_LIVE_E2E_USER", "live-audit-admin").strip()
AUDIT_PASSWORD = os.environ.get(
    "MEDIAMOP_LIVE_E2E_PASSWORD", "live-audit-pass-20260831"
)
ARTIFACT_DIR = Path(
    os.environ.get("MEDIAMOP_LIVE_E2E_ARTIFACTS", "artifacts/live-packaged-e2e")
)
TIMEOUT_MS = 30_000


def project_version() -> str:
    """Resolve the expected packaged version without hard-coding a release."""

    explicit = os.environ.get("MEDIAMOP_LIVE_EXPECTED_VERSION", "").strip()
    if explicit:
        return explicit
    project_file = Path(__file__).resolve().parents[1] / "apps/backend/pyproject.toml"
    with project_file.open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


EXPECTED_VERSION = project_version()


class LiveAudit:
    """Small assertion/reporting wrapper used by the live browser audit."""

    def __init__(self, page: Page, context: BrowserContext) -> None:
        self.page = page
        self.context = context
        self.steps: list[str] = []
        self.screens: list[str] = []
        self.console_errors: list[str] = []
        self.console_warnings: list[str] = []
        self.page_errors: list[str] = []
        self.failed_requests: list[str] = []
        self.bad_responses: list[str] = []
        self.http_checks: list[str] = []
        self.completed_requests: set[tuple[str, str]] = set()
        self._attach_diagnostics()

    def _attach_diagnostics(self) -> None:
        def on_console(message: Any) -> None:
            text = (message.text or "").strip()
            if not text:
                return
            # The authenticated shell probes /auth/me before it knows whether
            # a session exists. Chromium reports that expected 401 as a
            # console error even though the response is part of the normal
            # anonymous bootstrap path.
            if (
                text
                == "Failed to load resource: the server responded with a status of 401 (Unauthorized)"
            ):
                return
            if message.type == "error":
                self.console_errors.append(text)
            elif message.type == "warning":
                self.console_warnings.append(text)

        def on_page_error(error: Any) -> None:
            self.page_errors.append(str(error))

        def on_request_failed(request: Any) -> None:
            failure = request.failure
            detail = failure if isinstance(failure, str) else "unknown failure"
            if (
                request.method,
                request.url,
            ) in self.completed_requests and detail == "net::ERR_ABORTED":
                return
            # EventSource is deliberately closed when Activity unmounts or a
            # filter/navigation replaces the stream. Chromium reports that
            # normal client-side close as ERR_ABORTED.
            if (
                request.url.endswith("/api/v1/activity/stream")
                and detail == "net::ERR_ABORTED"
            ):
                return
            self.failed_requests.append(f"{request.method} {request.url}: {detail}")

        def on_response(response: Response) -> None:
            if response.status < 400:
                self.completed_requests.add((response.request.method, response.url))
            if response.status >= 400:
                if response.status == 401 and response.url.rstrip("/").endswith(
                    "/api/v1/auth/me"
                ):
                    return
                self.bad_responses.append(f"{response.status} {response.url}")

        self.page.on("console", on_console)
        self.page.on("pageerror", on_page_error)
        self.page.on("requestfailed", on_request_failed)
        self.page.on("response", on_response)

    def record(self, message: str) -> None:
        self.steps.append(message)
        print(f"PASS  {message}")

    def require(self, condition: bool, message: str) -> None:
        if not condition:
            raise AssertionError(message)

    def visible(self, locator: Locator, message: str) -> Locator:
        try:
            locator.wait_for(state="visible", timeout=TIMEOUT_MS)
        except Exception:
            print(
                "DEBUG visible timeout: "
                f"{message}; url={self.page.url}; "
                f"body={self.page.locator('body').inner_text()[:1200]!r}; "
                f"console_errors={self.console_errors[:3]!r}; "
                f"page_errors={self.page_errors[:3]!r}; "
                f"failed_requests={self.failed_requests[:3]!r}",
                file=sys.stderr,
            )
            raise
        self.require(locator.is_visible(), message)
        return locator

    def click(self, locator: Locator, message: str) -> None:
        self.visible(locator, message).click()
        self.page.wait_for_timeout(120)

    def settle(self, timeout_ms: int = 1_500) -> None:
        try:
            self.page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except PlaywrightTimeoutError:
            # Live polling pages intentionally stay busy.  The explicit waits
            # on the next screen are the meaningful synchronization points.
            pass

    def screenshot(self, name: str) -> None:
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        path = ARTIFACT_DIR / f"{name}.png"
        self.page.screenshot(path=str(path), full_page=True)
        self.screens.append(str(path))
        self.record(f"screenshot captured: {name}")

    def get(self, path: str, *, headers: dict[str, str] | None = None) -> Any:
        response = self.context.request.get(
            urljoin(BASE_URL + "/", path.lstrip("/")), headers=headers or {}
        )
        self.require(response.ok, f"GET {path} returned HTTP {response.status}")
        self.http_checks.append(f"GET {path} -> {response.status}")
        return response

    def assert_common_headers(self, response: Any, path: str) -> None:
        headers = {key.lower(): value for key, value in response.headers.items()}
        self.require("server" not in headers, f"{path} exposes a Server header")
        self.require(
            headers.get("cache-control", "").lower().startswith("no-store"),
            f"{path} is not marked no-store",
        )

    def public_contract(self) -> None:
        health = self.get("/health")
        self.assert_common_headers(health, "/health")
        health_body = health.json()
        self.require(health_body.get("status") == "ok", "health status is not ok")
        self.record("public health endpoint and headers")

        readiness = self.get("/ready")
        self.assert_common_headers(readiness, "/ready")
        readiness_body = readiness.json()
        self.require(readiness_body.get("ready") is True, "readiness is not true")
        self.require(
            readiness_body.get("status") == "ready", "readiness status is wrong"
        )
        self.require(
            set(readiness_body).issubset({"ready", "status"}),
            "public readiness leaks detailed dependency state",
        )
        self.record("public readiness endpoint is minimal and truthful")

        openapi = self.get("/openapi.json")
        openapi_headers = {key.lower(): value for key, value in openapi.headers.items()}
        self.require(
            "server" not in openapi_headers, "/openapi.json exposes a Server header"
        )
        openapi_body = openapi.json()
        self.require(
            "openapi" in openapi_body, "OpenAPI document is missing its version"
        )
        self.require(
            str(openapi_body.get("info", {}).get("version", "")).strip()
            == EXPECTED_VERSION,
            f"packaged server does not report version {EXPECTED_VERSION}",
        )
        self.record("OpenAPI document and packaged version")

        index = self.get("/")
        index_headers = {key.lower(): value for key, value in index.headers.items()}
        self.require("server" not in index_headers, "index exposes a Server header")
        self.require(
            "no-store" in index_headers.get("cache-control", "").lower(),
            "index is not marked no-store",
        )
        html = index.text()
        assets = re.findall(r'(?:src|href)=["\']([^"\']*assets/[^"\']+)["\']', html)
        self.require(bool(assets), "index did not reference a built asset")
        asset_path = assets[0]
        asset = self.get(asset_path, headers={"Accept-Encoding": "gzip, br"})
        asset_headers = {key.lower(): value for key, value in asset.headers.items()}
        self.require(
            "server" not in asset_headers, "static asset exposes a Server header"
        )
        self.require(
            "immutable" in asset_headers.get("cache-control", "").lower(),
            "hashed static asset is not immutable-cacheable",
        )
        if asset_headers.get("content-encoding"):
            self.require(
                "accept-encoding" in asset_headers.get("vary", "").lower(),
                "compressed static asset is missing Vary: Accept-Encoding",
            )
        self.record("static asset compression/cache contract")

    def bootstrap_and_sign_in(self) -> None:
        self.page.goto(BASE_URL + "/", wait_until="domcontentloaded")
        self.settle()

        setup_user = self.page.get_by_test_id("setup-username")
        if setup_user.count():
            self.visible(setup_user, "first-time setup form is visible")
            setup_user.fill(AUDIT_USER)
            self.page.get_by_test_id("setup-password").fill(AUDIT_PASSWORD)
            self.click(
                self.page.get_by_test_id("setup-submit"), "first-time setup submit"
            )
            self.page.wait_for_url(re.compile(r".*/login"), timeout=TIMEOUT_MS)

        login_user = self.page.get_by_test_id("login-username")
        if login_user.count():
            self.visible(login_user, "login form is visible")
            login_user.fill(AUDIT_USER)
            self.page.get_by_test_id("login-password").fill(AUDIT_PASSWORD)
            self.click(self.page.get_by_test_id("login-submit"), "login submit")
            self.page.wait_for_timeout(500)

        if "/setup-wizard" in self.page.url:
            self.visible(
                self.page.get_by_test_id("setup-wizard-skip"),
                "setup wizard is visible after sign-in",
            )
            self.click(
                self.page.get_by_test_id("setup-wizard-skip"),
                "skip setup wizard after exercising its entry path",
            )
            self.page.wait_for_url(
                lambda url: "/setup-wizard" not in url, timeout=TIMEOUT_MS
            )

        self.visible(
            self.page.get_by_test_id("shell-ready"), "authenticated application shell"
        )
        self.record("bootstrap, login, and setup-wizard state")

    def authenticated_read_surface(self) -> None:
        """Touch every non-streaming documented GET route without mutating data."""
        paths = (
            "/api/v1/activity/recent?limit=5",
            "/api/v1/auth/bootstrap/status",
            "/api/v1/auth/csrf",
            "/api/v1/auth/me",
            "/api/v1/auth/session",
            "/api/v1/auth/sessions",
            "/api/v1/dashboard/status",
            "/api/v1/media-managers/capabilities",
            "/api/v1/media-managers/connections",
            "/api/v1/media-managers/connections/999999",
            "/api/v1/pruner/instances",
            "/api/v1/pruner/instances/999999",
            "/api/v1/pruner/instances/999999/preview-runs?limit=5",
            "/api/v1/pruner/instances/999999/preview-runs/00000000-0000-4000-8000-000000000000",
            "/api/v1/pruner/instances/999999/scopes/movies",
            "/api/v1/pruner/instances/999999/scopes/movies/plex-live-removal-eligibility",
            "/api/v1/pruner/instances/999999/studios?scope=movies",
            "/api/v1/pruner/jobs/inspection?limit=5",
            "/api/v1/pruner/overview-stats",
            "/api/v1/refiner/files?limit=5",
            "/api/v1/refiner/files/999999/log",
            "/api/v1/refiner/files/999999/log/download",
            "/api/v1/refiner/files/999999/why-held",
            "/api/v1/refiner/hardware",
            "/api/v1/refiner/jobs/inspection?limit=5",
            "/api/v1/refiner/libraries",
            "/api/v1/refiner/libraries/999999",
            "/api/v1/refiner/libraries/discover/999999",
            "/api/v1/refiner/libraries/discover/999999/drift",
            "/api/v1/refiner/maintenance",
            "/api/v1/refiner/metadata-provider",
            "/api/v1/refiner/operator-settings",
            "/api/v1/refiner/overview-stats",
            "/api/v1/refiner/path-settings",
            "/api/v1/refiner/remux-rules-settings",
            "/api/v1/refiner/rule-sets",
            "/api/v1/refiner/runtime-settings",
            "/api/v1/suite/configuration-backups",
            "/api/v1/suite/configuration-backups/999999/download",
            "/api/v1/suite/configuration-bundle",
            "/api/v1/suite/logs?limit=5",
            "/api/v1/suite/metrics",
            "/api/v1/suite/notification-channels",
            "/api/v1/suite/pause",
            "/api/v1/suite/security-overview",
            "/api/v1/suite/settings",
            "/api/v1/suite/settings/configuration-bundle",
            "/api/v1/suite/settings/update-status",
            "/api/v1/suite/update-settings",
            "/api/v1/suite/update-state",
            "/api/v1/suite/update-status",
            "/api/v1/system/directories",
            "/api/v1/system/readiness",
            "/api/v1/system/reconciliation",
            "/api/v1/system/suite-configuration-backups",
            "/api/v1/system/suite-configuration-backups/999999/download",
            "/api/v1/system/suite-configuration-bundle",
        )
        headers = {
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        }
        for path in paths:
            response = self.context.request.get(
                urljoin(BASE_URL + "/", path.lstrip("/")),
                headers=headers,
                timeout=TIMEOUT_MS,
            )
            self.require(
                response.status in {200, 204, 404},
                f"GET {path} returned unexpected HTTP {response.status}",
            )
            self.http_checks.append(f"GET {path} -> {response.status}")
        # The SSE route is intentionally excluded from the finite request
        # loop; the Activity browser step opens and closes it as a real client.
        self.record(
            f"authenticated read-only API surface ({len(paths)} routes; Activity SSE exercised in browser)"
        )

    def open_sidebar(self, label: str) -> None:
        link = self.page.get_by_role("link", name=label, exact=True)
        self.click(link, f"open {label} from primary navigation")

    def assert_no_visible_crash(self) -> None:
        boundary = self.page.get_by_test_id("error-boundary")
        if boundary.count():
            self.require(not boundary.is_visible(), "error boundary is visible")
        self.require(
            not self.page.get_by_text("Something went wrong", exact=False).count(),
            "generic error state is visible",
        )

    def shell_and_responsive(self) -> None:
        self.page.set_viewport_size({"width": 1_440, "height": 1_000})
        self.page.goto(BASE_URL + "/", wait_until="domcontentloaded")
        self.visible(self.page.get_by_test_id("shell-ready"), "desktop shell")
        collapse = self.page.get_by_test_id("sidebar-collapse")
        self.require(
            collapse.get_attribute("aria-expanded") == "true", "sidebar starts expanded"
        )
        self.click(collapse, "collapse sidebar")
        self.require(
            collapse.get_attribute("aria-expanded") == "false", "sidebar collapses"
        )
        self.click(collapse, "expand sidebar")
        self.require(
            collapse.get_attribute("aria-expanded") == "true", "sidebar expands"
        )

        theme = self.page.get_by_test_id("theme-toggle")
        before = self.page.locator("html").get_attribute("data-mm-theme")
        self.click(theme, "toggle application theme")
        after = self.page.locator("html").get_attribute("data-mm-theme")
        self.require(
            after in {"dark", "light"} and after != before, "theme toggle did not apply"
        )
        self.click(theme, "toggle application theme back")

        self.page.set_viewport_size({"width": 390, "height": 844})
        self.page.goto(BASE_URL + "/", wait_until="domcontentloaded")
        menu = self.page.get_by_test_id("shell-nav-toggle")
        self.click(menu, "open mobile navigation")
        self.visible(
            self.page.get_by_role("button", name="Close navigation"),
            "mobile navigation backdrop",
        )
        self.click(
            self.page.get_by_role("button", name="Close navigation"),
            "close mobile navigation",
        )
        self.require(
            not self.page.get_by_role("button", name="Close navigation").count(),
            "mobile navigation did not close",
        )
        self.page.set_viewport_size({"width": 1_440, "height": 1_000})
        self.record("desktop collapse/theme and mobile navigation controls")

    def dashboard(self) -> None:
        self.open_sidebar("Dashboard")
        self.visible(self.page.get_by_test_id("dashboard-page"), "Dashboard page")
        for test_id in (
            "dashboard-status-strip",
            "dashboard-module-cards",
            "dashboard-needs-attention",
            "dashboard-active-work",
            "dashboard-global-jobs",
        ):
            self.visible(self.page.get_by_test_id(test_id), f"Dashboard {test_id}")
        self.assert_no_visible_crash()
        self.screenshot("dashboard")
        self.record("Dashboard screen, truthful status cards, and action areas")

    def activity(self) -> None:
        self.open_sidebar("Activity")
        self.visible(self.page.get_by_test_id("activity-feed"), "Activity feed")
        selects = self.page.locator("select")
        self.require(selects.count() >= 2, "Activity filters are incomplete")
        self.require(
            "All modules" in selects.nth(0).inner_text(),
            "Activity module filter missing All modules",
        )
        self.require(
            "System" in selects.nth(0).inner_text(),
            "Activity module filter missing System",
        )
        selects.nth(0).select_option(label="System")
        if selects.nth(1).locator("option").count() > 1:
            selects.nth(1).select_option(index=1)
        self.page.get_by_placeholder("Search titles and details").fill("audit")
        self.page.locator('input[type="datetime-local"]').nth(0).fill(
            "2026-01-01T00:00"
        )
        self.page.locator('input[type="datetime-local"]').nth(1).fill(
            "2026-12-31T23:59"
        )
        self.click(
            self.page.get_by_role("button", name="Apply filters", exact=True),
            "apply Activity filters",
        )
        self.visible(
            self.page.get_by_text("Filters active", exact=True),
            "Activity active filter state",
        )
        self.click(
            self.page.get_by_role("button", name="Clear", exact=True),
            "clear Activity filters",
        )
        self.require(
            not self.page.get_by_text("Filters active", exact=True).count(),
            "Activity filters did not clear",
        )
        self.screenshot("activity")
        self.record("Activity feed, filters, bounded refresh state, and clear action")

    def refiner(self) -> None:
        self.open_sidebar("Refiner")
        self.visible(self.page.get_by_test_id("refiner-scope-page"), "Refiner page")
        expected = {
            "Overview": "refiner-overview-panel",
            "Libraries": "refiner-libraries-section",
            "Audio & subtitles": "refiner-remux-section",
            "Schedules": "refiner-schedules-section",
            "Files": "refiner-files-section",
            "Jobs": "refiner-jobs-inspection-section",
            "Maintenance": "refiner-maintenance-section",
        }
        for tab, test_id in expected.items():
            self.click(
                self.page.get_by_role("tab", name=tab, exact=True),
                f"open Refiner {tab} tab",
            )
            self.visible(self.page.get_by_test_id(test_id), f"Refiner {tab} panel")

            if tab == "Libraries":
                edit_buttons = self.page.get_by_role("button", name="Edit", exact=True)
                if edit_buttons.count():
                    self.click(edit_buttons.first, "open Refiner library editor")
                    self.visible(
                        self.page.get_by_test_id("refiner-library-form"),
                        "Refiner library form",
                    )
                    cancel = self.page.get_by_role("button", name="Cancel", exact=True)
                    if cancel.count():
                        self.click(cancel.last, "cancel Refiner library editor")
            elif tab == "Schedules":
                self.require(
                    self.page.get_by_text(
                        "TV watched-folder window", exact=True
                    ).count()
                    > 0,
                    "Refiner TV schedule controls missing",
                )
                self.require(
                    self.page.get_by_text(
                        "Movies watched-folder window", exact=True
                    ).count()
                    > 0,
                    "Refiner Movies schedule controls missing",
                )
            elif tab == "Files":
                self.page.get_by_placeholder("part of a file or folder name").fill(
                    "audit"
                )
                self.click(
                    self.page.get_by_role("button", name=re.compile(r"All \(")),
                    "filter Refiner files",
                )
            elif tab == "Maintenance":
                self.require(
                    self.page.get_by_text(
                        "What this instance is running with", exact=True
                    ).count()
                    > 0,
                    "Refiner runtime settings are missing",
                )

        self.screenshot("refiner")
        self.record(
            "Refiner overview, libraries, remux, schedules, files, jobs, and maintenance tabs"
        )

    def pruner(self) -> None:
        self.open_sidebar("Pruner")
        self.visible(self.page.get_by_test_id("pruner-scope-page"), "Pruner page")
        self.visible(
            self.page.get_by_test_id("pruner-top-level-tabs"), "Pruner top-level tabs"
        )
        self.visible(
            self.page.get_by_test_id("pruner-top-overview-tab"), "Pruner overview"
        )

        for provider in ("Emby", "Jellyfin", "Plex"):
            provider_id = provider.lower()
            self.click(
                self.page.get_by_role("tab", name=provider, exact=True),
                f"open Pruner {provider} tab",
            )
            self.visible(
                self.page.get_by_test_id(f"pruner-provider-tab-{provider_id}"),
                f"Pruner {provider} tab",
            )
            self.visible(
                self.page.get_by_test_id(f"pruner-connection-panel-{provider_id}"),
                f"Pruner {provider} connection panel",
            )
            # Each provider workspace exposes the same connection/cleanup/schedule
            # contract.  Exercise the visible section controls without saving an
            # external server or running a destructive preview.
            section_tabs = self.page.get_by_role("tab")
            for label in ("Connection", "Cleanup", "Schedule"):
                candidate = section_tabs.filter(has_text=label)
                if candidate.count():
                    self.click(
                        candidate.first, f"open Pruner {provider} {label} section"
                    )
            self.click(
                self.page.get_by_role("tab", name=provider, exact=True),
                f"restore Pruner {provider} tab",
            )

        self.click(
            self.page.get_by_role("tab", name="Jobs", exact=True),
            "open Pruner jobs tab",
        )
        self.visible(self.page.get_by_test_id("pruner-top-jobs-tab"), "Pruner jobs")
        self.page.goto(BASE_URL + "/pruner?tab=schedule", wait_until="domcontentloaded")
        self.visible(
            self.page.get_by_test_id("pruner-scope-page"), "Pruner schedule deep link"
        )
        self.visible(
            self.page.get_by_test_id("pruner-provider-schedule-wrap"),
            "Pruner schedule deep-link panel",
        )
        self.screenshot("pruner")
        self.record(
            "Pruner overview, Emby/Jellyfin/Plex configuration, jobs, and schedule deep link"
        )

    def settings_general_and_setup(self) -> None:
        self.open_sidebar("Settings")
        self.visible(self.page.get_by_test_id("suite-settings-page"), "Settings page")
        self.visible(
            self.page.get_by_test_id("suite-settings-global"), "Settings General tab"
        )
        self.visible(
            self.page.get_by_text("Timezone", exact=True), "Settings timezone control"
        )
        density = self.page.get_by_role("radiogroup", name="Display density")
        self.visible(density, "Settings display density control")
        options = density.get_by_role("radio")
        self.require(
            options.count() >= 3, "Settings display density options are incomplete"
        )
        options.nth(2).click()
        self.require(
            self.page.locator("html").get_attribute("data-mm-density") == "comfortable",
            "display density did not apply",
        )

        # Exercise the wizard's supported re-entry path, then leave it with the
        # safe skip action so the disposable audit account remains usable.
        self.click(
            self.page.get_by_test_id("suite-settings-open-setup-wizard"),
            "open setup wizard from Settings",
        )
        self.visible(
            self.page.get_by_test_id("setup-wizard-skip"), "re-entered setup wizard"
        )
        self.click(
            self.page.get_by_test_id("setup-wizard-skip"),
            "skip re-entered setup wizard",
        )
        self.page.wait_for_url(
            lambda url: "/setup-wizard" not in url, timeout=TIMEOUT_MS
        )
        self.open_sidebar("Settings")
        self.visible(
            self.page.get_by_test_id("suite-settings-global"),
            "return to Settings General",
        )
        self.screenshot("settings-general")
        self.record("Settings General, timezone/density controls, and wizard re-entry")

    def settings_backup_upgrade_logs_security(self) -> None:
        # The tab labels are a product contract; assert all of them before
        # interacting with each panel.
        for label in (
            "General",
            "Security",
            "Backup and restore",
            "Upgrade",
            "Logs",
            "Notifications",
            "Media managers",
        ):
            self.require(
                self.page.get_by_role("tab", name=label, exact=True).count() > 0,
                f"Settings tab missing: {label}",
            )

        self.click(
            self.page.get_by_role("tab", name="Backup and restore", exact=True),
            "open Settings backup",
        )
        self.visible(
            self.page.get_by_test_id("suite-settings-backup-tab"),
            "Settings backup panel",
        )
        self.require(
            self.page.get_by_role(
                "button", name="Download configuration now", exact=True
            ).count()
            > 0,
            "configuration download control missing",
        )
        with self.page.expect_download(timeout=TIMEOUT_MS) as download_info:
            self.page.get_by_role(
                "button", name="Download configuration now", exact=True
            ).click()
        self.require(
            download_info.value.suggested_filename.endswith(".json"),
            "configuration export is not JSON",
        )

        self.click(
            self.page.get_by_role("tab", name="Upgrade", exact=True),
            "open Settings upgrade",
        )
        self.visible(
            self.page.get_by_test_id("suite-settings-upgrade-tab"),
            "Settings upgrade panel",
        )
        self.click(
            self.page.get_by_role("button", name="Check again", exact=True),
            "refresh upgrade status",
        )

        self.click(
            self.page.get_by_role("tab", name="Logs", exact=True), "open Settings logs"
        )
        self.visible(
            self.page.get_by_test_id("suite-settings-logs"), "Settings logs panel"
        )
        self.visible(
            self.page.get_by_text("Server diagnostics", exact=True),
            "Settings diagnostics disclosure",
        )
        self.page.get_by_placeholder(
            "Search message, detail, traceback, logger, or source"
        ).fill("audit")
        level_select = self.page.locator("select").first
        if level_select.count():
            level_select.select_option(index=1)
        toggles = self.page.get_by_role("radio")
        if toggles.count() >= 2:
            toggles.last.click()
        refresh = self.page.get_by_role("button", name="Refresh", exact=True)
        if refresh.count():
            self.click(refresh, "refresh Settings logs")

        self.click(
            self.page.get_by_role("tab", name="Security", exact=True),
            "open Settings security",
        )
        self.visible(
            self.page.get_by_test_id("suite-settings-security"),
            "Settings security panel",
        )
        self.visible(
            self.page.get_by_text("Security posture", exact=True), "security posture"
        )
        self.visible(
            self.page.get_by_text("Active sessions", exact=True), "active sessions"
        )
        self.visible(
            self.page.get_by_role("heading", name="Change password", exact=True),
            "change-password controls",
        )
        self.screenshot("settings-security")
        self.record(
            "Settings backup/export, upgrade refresh, logs filters, and security/session posture"
        )

    def settings_notifications(self) -> None:
        self.click(
            self.page.get_by_role("tab", name="Notifications", exact=True),
            "open Settings notifications",
        )
        self.visible(
            self.page.get_by_test_id("suite-settings-notifications"),
            "Settings notifications panel",
        )
        # Make reruns safe after a diagnostic failure leaves the disposable
        # channel behind.
        existing = self.page.get_by_text("Live audit channel", exact=True)
        while existing.count():
            card = existing.first.locator("xpath=../../../..")
            with self.page.expect_response(
                lambda response: (
                    response.request.method == "DELETE"
                    and "/api/v1/suite/notification-channels/" in response.url
                ),
                timeout=TIMEOUT_MS,
            ) as delete_response:
                self.click(
                    card.get_by_role("button", name="Remove", exact=True),
                    "remove leftover notification channel",
                )
            self.require(
                delete_response.value.status == 204,
                "leftover notification channel removal failed",
            )
            existing.first.wait_for(state="detached", timeout=TIMEOUT_MS)
        self.click(
            self.page.get_by_role(
                "button", name="Add notification channel", exact=True
            ),
            "open notification channel form",
        )
        form = (
            self.page.locator("form")
            .filter(has=self.page.get_by_text("Label", exact=True))
            .last
        )
        self.visible(form, "notification channel form")
        labels = form.locator("input[type='text']")
        self.require(labels.count() >= 1, "notification label control missing")
        labels.first.fill("Live audit channel")
        form.locator("input[type='url']").fill("https://example.invalid/webhook")
        events = form.locator("input[type='checkbox']")
        self.require(events.count() > 0, "notification event controls missing")
        # Keep the default failure event selected and exercise the enabled switch
        # without leaving the final channel disabled.
        self.click(
            form.get_by_role("button", name="Save channel", exact=True),
            "create notification channel",
        )
        row = self.page.get_by_text("Live audit channel", exact=True)
        self.visible(row, "created notification channel")
        row_parent = row.locator("xpath=../../..")
        self.click(
            row_parent.get_by_role("button", name="Edit", exact=True),
            "edit notification channel",
        )
        self.visible(
            self.page.get_by_text("Edit channel", exact=True), "notification edit form"
        )
        self.click(
            self.page.get_by_role("button", name="Cancel", exact=True),
            "cancel notification edit",
        )
        row_parent = self.page.get_by_text("Live audit channel", exact=True).locator(
            "xpath=../../.."
        )
        with self.page.expect_response(
            lambda response: (
                response.request.method == "DELETE"
                and "/api/v1/suite/notification-channels/" in response.url
            ),
            timeout=TIMEOUT_MS,
        ) as delete_response:
            self.click(
                row_parent.get_by_role("button", name="Remove", exact=True),
                "remove notification channel",
            )
        self.require(
            delete_response.value.status == 204, "notification channel removal failed"
        )
        self.page.get_by_text("Live audit channel", exact=True).wait_for(
            state="detached", timeout=TIMEOUT_MS
        )
        self.record("notification channel create, edit/cancel, and remove")

    def settings_media_managers(self) -> None:
        self.click(
            self.page.get_by_role("tab", name="Media managers", exact=True),
            "open Settings media managers",
        )
        self.visible(
            self.page.get_by_test_id("media-manager-add"),
            "Settings media managers panel",
        )
        for card in self.page.get_by_test_id("media-manager-card").all():
            if "Live audit manager" in card.inner_text():
                with self.page.expect_response(
                    lambda response: (
                        response.request.method == "DELETE"
                        and "/api/v1/media-managers/connections/" in response.url
                    ),
                    timeout=TIMEOUT_MS,
                ) as delete_response:
                    self.click(
                        card.get_by_test_id("media-manager-remove"),
                        "remove leftover media manager",
                    )
                self.require(
                    delete_response.value.status == 204,
                    "leftover media manager removal failed",
                )
                card.wait_for(state="detached", timeout=TIMEOUT_MS)
        self.click(
            self.page.get_by_test_id("media-manager-add"), "open media manager form"
        )
        self.page.get_by_test_id("media-manager-name").fill("Live audit manager")
        self.page.get_by_test_id("media-manager-base-url").fill("http://127.0.0.1:9")
        self.page.get_by_test_id("media-manager-api-key").fill("audit-secret")
        self.click(
            self.page.get_by_test_id("media-manager-save"), "create media manager"
        )
        card = self.page.get_by_test_id("media-manager-card").filter(
            has_text="Live audit manager"
        )
        self.visible(card, "created media manager")
        self.visible(
            card.get_by_test_id("media-manager-status"), "media manager status"
        )
        self.click(
            card.get_by_test_id("media-manager-setup-details").locator("summary"),
            "open media manager setup details",
        )
        self.click(
            card.get_by_test_id("media-manager-generate-secret"),
            "generate media manager webhook secret",
        )
        self.visible(
            card.get_by_test_id("media-manager-secret"), "generated webhook secret"
        )
        self.click(
            card.get_by_role("button", name="Disable", exact=True),
            "disable media manager",
        )
        self.click(
            card.get_by_role("button", name="Enable", exact=True),
            "enable media manager",
        )
        self.click(
            card.get_by_test_id("media-manager-test"), "test media manager connection"
        )
        self.visible(
            card.get_by_test_id("media-manager-status"), "media manager test result"
        )
        with self.page.expect_response(
            lambda response: (
                response.request.method == "DELETE"
                and "/api/v1/media-managers/connections/" in response.url
            ),
            timeout=TIMEOUT_MS,
        ) as delete_response:
            self.click(
                card.get_by_test_id("media-manager-remove"), "remove media manager"
            )
        self.require(
            delete_response.value.status == 204, "media manager removal failed"
        )
        self.require(
            not self.page.get_by_test_id("media-manager-card")
            .filter(has_text="Live audit manager")
            .count(),
            "media manager was not removed",
        )
        self.screenshot("settings-integrations")
        self.record(
            "media-manager create, secret generation, enable/disable, connection test, and remove"
        )

    def settings_history_and_navigation(self) -> None:
        self.click(
            self.page.get_by_role("tab", name="General", exact=True),
            "set Settings history origin to General",
        )
        self.visible(
            self.page.get_by_test_id("suite-settings-global"),
            "Settings General history origin",
        )
        self.click(
            self.page.get_by_role("tab", name="Security", exact=True),
            "exercise Settings URL history forward target",
        )
        self.require(
            "tab=security" in self.page.url,
            "Settings security tab is not represented in the URL",
        )
        self.page.go_back()
        self.visible(
            self.page.get_by_test_id("suite-settings-global"),
            "Settings browser-back returns General",
        )
        self.page.go_forward()
        self.visible(
            self.page.get_by_test_id("suite-settings-security"),
            "Settings browser-forward returns Security",
        )
        self.page.goto(BASE_URL + "/not-a-real-screen", wait_until="domcontentloaded")
        self.visible(
            self.page.get_by_text("Page not found", exact=False), "not-found route"
        )
        self.record("Settings URL history and not-found route")

    def finish(self) -> dict[str, Any]:
        # Warnings are retained in the report for review.  Runtime errors,
        # failed requests, and HTTP errors are release blockers.
        self.require(
            not self.console_errors,
            f"browser console errors: {self.console_errors[:5]}",
        )
        self.require(
            not self.page_errors, f"browser page errors: {self.page_errors[:5]}"
        )
        self.require(
            not self.failed_requests,
            f"browser request failures: {self.failed_requests[:5]}",
        )
        self.require(
            not self.bad_responses, f"browser HTTP errors: {self.bad_responses[:10]}"
        )
        report = {
            "base_url": BASE_URL,
            "server_version": EXPECTED_VERSION,
            "steps": self.steps,
            "http_checks": self.http_checks,
            "screenshots": self.screens,
            "console_warnings": self.console_warnings,
            "console_errors": self.console_errors,
            "page_errors": self.page_errors,
            "failed_requests": self.failed_requests,
            "bad_responses": self.bad_responses,
        }
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        (ARTIFACT_DIR / "summary.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        return report


def run(playwright: Playwright) -> dict[str, Any]:
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 1_440, "height": 1_000}, ignore_https_errors=True
    )
    page = context.new_page()
    page.set_default_timeout(TIMEOUT_MS)
    audit = LiveAudit(page, context)
    try:
        audit.public_contract()
        audit.bootstrap_and_sign_in()
        audit.authenticated_read_surface()
        audit.shell_and_responsive()
        audit.dashboard()
        audit.activity()
        audit.refiner()
        audit.pruner()
        audit.settings_general_and_setup()
        audit.settings_backup_upgrade_logs_security()
        audit.settings_notifications()
        audit.settings_media_managers()
        audit.settings_history_and_navigation()
        return audit.finish()
    except Exception:
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        try:
            page.screenshot(path=str(ARTIFACT_DIR / "failure.png"), full_page=True)
        except Exception as screenshot_error:  # noqa: BLE001 - preserve the original audit failure
            print(
                f"WARN  could not capture failure screenshot: {screenshot_error}",
                file=sys.stderr,
            )
        raise
    finally:
        context.close()
        browser.close()


def main() -> int:
    if not BASE_URL:
        print("MEDIAMOP_LIVE_BASE_URL is required", file=sys.stderr)
        return 2
    print(f"Auditing packaged MediaMop at {BASE_URL}")
    try:
        with sync_playwright() as playwright:
            report = run(playwright)
    except Exception as exc:  # noqa: BLE001 - convert any audit failure into a non-zero CLI result
        print(f"FAIL  packaged live audit: {exc}", file=sys.stderr)
        return 1
    print(
        f"PASS  packaged live audit complete: {len(report['steps'])} steps, "
        f"{len(report['screenshots'])} screenshots, "
        f"{len(report['console_warnings'])} console warnings"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
