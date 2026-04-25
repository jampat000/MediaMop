import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import { DISPLAY_DENSITY_STORAGE_KEY } from "../../lib/ui/display-density";
import type { UserPublic } from "../../lib/api/types";
import { qk } from "../../lib/auth/queries";
import {
  suiteConfigurationBackupsQueryKey,
  suiteLogsQueryKey,
  suiteMetricsQueryKey,
  suiteSecurityOverviewQueryKey,
  suiteSettingsQueryKey,
  suiteUpdateStatusQueryKey,
} from "../../lib/suite/queries";
import type { SuiteLogsOut, SuiteMetricsOut, SuiteSecurityOverviewOut, SuiteSettingsOut, SuiteUpdateStatusOut } from "../../lib/suite/types";
import { SettingsPage } from "./settings-page";

const operatorMe: UserPublic = { id: 1, username: "alice", role: "operator" };
const viewerMe: UserPublic = { id: 2, username: "bob", role: "viewer" };

const minimalSuiteSettings: SuiteSettingsOut = {
  product_display_name: "MediaMop",
  signed_in_home_notice: null,
  setup_wizard_state: "pending",
  app_timezone: "UTC",
  log_retention_days: 30,
  configuration_backup_enabled: false,
  configuration_backup_interval_hours: 24,
  configuration_backup_last_run_at: null,
  updated_at: "2026-04-11T00:00:00Z",
};

const minimalUpdateStatus: SuiteUpdateStatusOut = {
  current_version: "1.0.0",
  install_type: "source",
  status: "up_to_date",
  summary: "This install is already on MediaMop 1.0.0.",
  latest_version: "1.0.0",
  latest_name: "MediaMop 1.0.0",
  published_at: null,
  release_url: "https://example.com/release",
  windows_installer_url: null,
  docker_image: null,
  docker_tag: null,
  docker_update_command: null,
};

const minimalSecurity: SuiteSecurityOverviewOut = {
  session_signing_configured: true,
  sign_in_cookie_https_only: false,
  sign_in_cookie_same_site: "Lax (recommended for most setups)",
  extra_https_hardening_enabled: false,
  sign_in_attempt_limit: 30,
  sign_in_attempt_window_plain: "1 minute",
  first_time_setup_attempt_limit: 10,
  first_time_setup_attempt_window_plain: "1 hour",
  allowed_browser_origins_count: 1,
  restart_required_note:
    "These safety options are read when the app starts from the server configuration file. To change them, ask whoever runs the server to edit that file and restart the app.",
};

const minimalLogs: SuiteLogsOut = {
  items: [],
  total: 0,
  counts: {
    error: 0,
    warning: 0,
    information: 0,
  },
};

const minimalMetrics: SuiteMetricsOut = {
  uptime_seconds: 3600,
  total_requests: 20,
  average_response_ms: 12,
  error_log_count: 0,
  status_counts: { "2xx": 18, "3xx": 0, "4xx": 2, "5xx": 0 },
  busiest_routes: [],
};

function wrap(ui: ReactNode, client: QueryClient) {
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

function renderSettings(me: UserPublic) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  qc.setQueryData(suiteSettingsQueryKey, minimalSuiteSettings);
  qc.setQueryData(suiteSecurityOverviewQueryKey, minimalSecurity);
  qc.setQueryData(qk.me, me);
  qc.setQueryData(suiteConfigurationBackupsQueryKey, { directory: "C:/MediaMop/backups/suite-configuration", items: [] });
  qc.setQueryData(suiteUpdateStatusQueryKey, minimalUpdateStatus);
  qc.setQueryData([...suiteLogsQueryKey, { level: undefined, search: undefined, has_exception: undefined, limit: 100 }], minimalLogs);
  qc.setQueryData(suiteMetricsQueryKey, minimalMetrics);
  return render(wrap(<SettingsPage />, qc));
}

describe("SettingsPage (suite settings)", () => {
  beforeEach(() => {
    localStorage.removeItem(DISPLAY_DENSITY_STORAGE_KEY);
    document.documentElement.removeAttribute("data-mm-density");
  });

  it("does not mention Sonarr or Radarr on the central Settings page", () => {
    const { container } = renderSettings(operatorMe);
    const t = (container.textContent ?? "").toLowerCase();
    expect(t).not.toContain("sonarr");
    expect(t).not.toContain("radarr");
    expect(screen.getByTestId("suite-settings-page")).toBeTruthy();
    expect(screen.getByTestId("suite-settings-global")).toBeTruthy();
  });

  it("hides save for viewers", () => {
    renderSettings(viewerMe);
    expect(screen.getByTestId("suite-settings-save-timezone")).toBeDisabled();
    expect(screen.getByTestId("suite-settings-save-logs")).toBeDisabled();
  });

  it("shows configuration backup + export for operators", () => {
    renderSettings(operatorMe);
    expect(screen.getByTestId("suite-settings-backup-restore")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Download configuration now" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Restore from file…" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Save backup schedule" })).toBeDisabled();
  });

  it("hides configuration backup for viewers", () => {
    renderSettings(viewerMe);
    expect(screen.queryByTestId("suite-settings-backup-restore")).not.toBeInTheDocument();
  });

  it("keeps General tab focused and splits Logs to its own tab", () => {
    renderSettings(operatorMe);
    expect(screen.queryByText("Product name")).not.toBeInTheDocument();
    expect(screen.queryByText("Application logs")).not.toBeInTheDocument();
    expect(screen.getByText("Timezone")).toBeInTheDocument();
    expect(screen.getByText("Setup wizard")).toBeInTheDocument();
    expect(screen.getByText("Upgrade")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "General" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Log retention (days)")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Logs" }));
    expect(screen.getByText("Search logs")).toBeInTheDocument();
    expect(screen.getByText("System events")).toBeInTheDocument();
    expect(screen.getByText("Server diagnostics")).toBeInTheDocument();
    expect(screen.queryByText("Log retention (days)")).not.toBeInTheDocument();
    expect(screen.queryByText("Optional home dashboard notice")).not.toBeInTheDocument();
  });

  it("shows change password only on Security tab", () => {
    renderSettings(operatorMe);
    fireEvent.click(screen.getByRole("tab", { name: "Security" }));
    expect(screen.getByRole("heading", { name: "Change password" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Security posture" })).not.toBeInTheDocument();
  });

  it("change password fields use Show/Hide and reset visibility when cleared", () => {
    renderSettings(operatorMe);
    fireEvent.click(screen.getByRole("tab", { name: "Security" }));
    const current = screen.getByPlaceholderText("Enter current password");
    expect(current).toHaveAttribute("type", "password");
    fireEvent.change(current, { target: { value: "current-secret" } });
    const showButtons = screen.getAllByRole("button", { name: "Show" });
    expect(showButtons.length).toBe(3);
    fireEvent.click(showButtons[0]!);
    expect(current).toHaveAttribute("type", "text");
    fireEvent.change(current, { target: { value: "" } });
    expect(current).toHaveAttribute("type", "password");
  });

  it("closes timezone dropdown and shows selected timezone", () => {
    renderSettings(operatorMe);
    const trigger = screen.getByRole("button", { name: /Timezone/ });
    expect(trigger).toHaveTextContent("Select timezone");
    fireEvent.click(trigger);
    const firstOption = screen.getAllByRole("option")[0];
    const chosenLabel = firstOption.textContent ?? "";
    fireEvent.mouseDown(firstOption);
    fireEvent.click(firstOption);
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Timezone/ })).toHaveTextContent(chosenLabel);
  });

  it("closes timezone dropdown on outside click", () => {
    renderSettings(operatorMe);
    const trigger = screen.getByRole("button", { name: /Timezone/ });
    fireEvent.click(trigger);
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("closes timezone dropdown on Escape", () => {
    renderSettings(operatorMe);
    const trigger = screen.getByRole("button", { name: /Timezone/ });
    fireEvent.click(trigger);
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("applies display density locally without suite save", () => {
    renderSettings(viewerMe);
    expect(screen.getByTestId("suite-settings-display-density")).toBeTruthy();
    fireEvent.click(screen.getByText("Comfortable"));
    expect(document.documentElement.getAttribute("data-mm-density")).toBe("comfortable");
    fireEvent.click(screen.getByText("Expanded"));
    expect(document.documentElement.getAttribute("data-mm-density")).toBe("expanded");
    fireEvent.click(screen.getByText("Balanced"));
    expect(document.documentElement.getAttribute("data-mm-density")).toBeNull();
  });
});
