import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { browserWindow } from "../../lib/browser-window";
import { DISPLAY_DENSITY_STORAGE_KEY } from "../../lib/ui/display-density";
import type { CurrentSession, UserPublic } from "../../lib/api/types";
import { qk } from "../../lib/auth/queries";
import * as suiteSettingsApi from "../../lib/suite/suite-settings-api";
import {
  suiteConfigurationBackupsQueryKey,
  suiteLogsQueryKey,
  suiteMetricsQueryKey,
  suiteSecurityOverviewQueryKey,
  suiteSettingsQueryKey,
  suiteUpdateStatusQueryKey,
} from "../../lib/suite/queries";
import type {
  SuiteLogsOut,
  SuiteMetricsOut,
  SuiteSecurityOverviewOut,
  SuiteSettingsOut,
  SuiteUpdateDiagnosticsOut,
  SuiteUpdateStatusOut,
} from "../../lib/suite/types";
import { SettingsPage, verifiedUpgradeRefreshKey } from "./settings-page";
const UPGRADE_HISTORY_STORAGE_KEY = "mediamop.upgrade.history.v1";

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
  configuration_backup_preferred_time: "02:00",
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
  in_app_upgrade_supported: false,
  in_app_upgrade_summary: null,
};

const windowsUpdateAvailableStatus: SuiteUpdateStatusOut = {
  ...minimalUpdateStatus,
  current_version: "2.0.7",
  install_type: "windows",
  status: "update_available",
  summary: "MediaMop 2.0.8 is available.",
  latest_version: "2.0.8",
  latest_name: "MediaMop 2.0.8",
  windows_installer_url:
    "https://github.com/jampat000/MediaMop/releases/download/v2.0.8/MediaMopSetup.exe",
  in_app_upgrade_supported: true,
  in_app_upgrade_summary:
    "Remote in-app upgrade is ready on this Windows install.",
};

const minimalSecurity: SuiteSecurityOverviewOut = {
  session_signing_configured: true,
  sign_in_cookie_https_only: false,
  sign_in_cookie_same_site: "Lax (recommended for most setups)",
  standard_session_idle_timeout_plain: "14 days",
  standard_session_absolute_timeout_plain: "90 days",
  trusted_session_idle_timeout_plain: "60 days",
  trusted_session_absolute_timeout_plain: "365 days",
  extra_https_hardening_enabled: false,
  sign_in_attempt_limit: 30,
  sign_in_attempt_window_plain: "1 minute",
  first_time_setup_attempt_limit: 10,
  first_time_setup_attempt_window_plain: "1 hour",
  allowed_browser_origins_count: 1,
  restart_required_note:
    "These safety options are read when the app starts from the server configuration file. To change them, ask whoever runs the server to edit that file and restart the app.",
};

const minimalCurrentSession: CurrentSession = {
  trusted_device: true,
  created_at: "2026-04-11T00:00:00Z",
  last_seen_at: "2026-04-11T00:05:00Z",
  absolute_expires_at: "2027-04-11T00:00:00Z",
  idle_timeout_minutes: 86400,
  absolute_timeout_days: 365,
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

type SuiteUpgradeProgress = NonNullable<SuiteUpdateStatusOut["upgrade"]>;

function upgradeProgress(
  overrides: Pick<SuiteUpgradeProgress, "phase" | "message"> &
    Partial<SuiteUpgradeProgress>,
): SuiteUpgradeProgress {
  const { phase, message, ...rest } = overrides;
  const isActiveByDefault = !["completed", "failed", "idle"].includes(phase);
  return {
    phase,
    message,
    is_active: isActiveByDefault,
    is_stale: false,
    blocks_new_update: isActiveByDefault,
    ...rest,
  };
}

function wrap(ui: ReactNode, client: QueryClient) {
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

function renderSettings(
  me: UserPublic,
  overrides?: {
    updateStatus?: SuiteUpdateStatusOut;
    initialEntries?: string[];
  },
) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  qc.setQueryData(suiteSettingsQueryKey, minimalSuiteSettings);
  qc.setQueryData(suiteSecurityOverviewQueryKey, minimalSecurity);
  qc.setQueryData(qk.me, me);
  qc.setQueryData(qk.session, minimalCurrentSession);
  qc.setQueryData(suiteConfigurationBackupsQueryKey, {
    directory: "C:/MediaMop/backups/suite-configuration",
    items: [],
  });
  qc.setQueryData(
    suiteUpdateStatusQueryKey,
    overrides?.updateStatus ?? minimalUpdateStatus,
  );
  qc.setQueryData(
    [
      ...suiteLogsQueryKey,
      {
        level: undefined,
        search: undefined,
        has_exception: undefined,
        limit: 100,
      },
    ],
    minimalLogs,
  );
  qc.setQueryData(suiteMetricsQueryKey, minimalMetrics);
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={overrides?.initialEntries}>
        <SettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function renderSettingsWithSupportConfig(
  me: UserPublic,
  supportConfig: {
    showCard: boolean;
    showPlaceholder: boolean;
    supportUrl: string | null;
  },
  overrides?: { updateStatus?: SuiteUpdateStatusOut },
) {
  vi.resetModules();
  vi.doMock("../../lib/support", () => ({
    SHOW_SUPPORT_CARD: supportConfig.showCard,
    SHOW_SUPPORT_URL_PLACEHOLDER: supportConfig.showPlaceholder,
    SUPPORT_URL: supportConfig.supportUrl,
  }));

  const { SettingsPage: SettingsPageWithMockedSupport } =
    await import("./settings-page");

  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  qc.setQueryData(suiteSettingsQueryKey, minimalSuiteSettings);
  qc.setQueryData(suiteSecurityOverviewQueryKey, minimalSecurity);
  qc.setQueryData(qk.me, me);
  qc.setQueryData(qk.session, minimalCurrentSession);
  qc.setQueryData(suiteConfigurationBackupsQueryKey, {
    directory: "C:/MediaMop/backups/suite-configuration",
    items: [],
  });
  qc.setQueryData(
    suiteUpdateStatusQueryKey,
    overrides?.updateStatus ?? minimalUpdateStatus,
  );
  qc.setQueryData(
    [
      ...suiteLogsQueryKey,
      {
        level: undefined,
        search: undefined,
        has_exception: undefined,
        limit: 100,
      },
    ],
    minimalLogs,
  );
  qc.setQueryData(suiteMetricsQueryKey, minimalMetrics);
  return render(wrap(<SettingsPageWithMockedSupport />, qc));
}

describe("SettingsPage (suite settings)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.removeItem(DISPLAY_DENSITY_STORAGE_KEY);
    localStorage.removeItem(UPGRADE_HISTORY_STORAGE_KEY);
    document.documentElement.removeAttribute("data-mm-density");
  });

  afterEach(() => {
    vi.doUnmock("../../lib/support");
    vi.resetModules();
  });

  it("does not mention Sonarr or Radarr on the central Settings page", () => {
    const { container } = renderSettings(operatorMe);
    const t = (container.textContent ?? "").toLowerCase();
    expect(t).not.toContain("sonarr");
    expect(t).not.toContain("radarr");
    expect(screen.getByTestId("suite-settings-page")).toBeTruthy();
    expect(screen.getByTestId("suite-settings-global")).toBeTruthy();
  });

  it("shows development support guidance inside the Support tab without a button when URL is missing", () => {
    renderSettings(operatorMe);
    expect(
      screen.queryByTestId("suite-settings-support"),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Support" }));
    expect(screen.getByTestId("suite-settings-support")).toBeInTheDocument();
    expect(
      screen.getByText("MediaMop is free to use. Support is optional."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "If MediaMop saves you time or helps keep your library cleaner, you can support ongoing development.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/Development note: set/i)).toBeInTheDocument();
    expect(screen.getByText("VITE_SUPPORT_URL")).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Support MediaMop" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/supporter licence/i)).not.toBeInTheDocument();
  });

  it("shows the Support settings destination and button when a valid support URL is configured", async () => {
    await renderSettingsWithSupportConfig(operatorMe, {
      showCard: true,
      showPlaceholder: false,
      supportUrl: "https://example.com/support",
    });

    fireEvent.click(screen.getByRole("tab", { name: "Support" }));

    expect(screen.getByTestId("suite-settings-support")).toBeInTheDocument();
    expect(
      screen.getByText("MediaMop is free to use. Support is optional."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "If MediaMop saves you time or helps keep your library cleaner, you can support ongoing development.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Support MediaMop" }),
    ).toHaveAttribute("href", "https://example.com/support");
    expect(screen.queryByText("VITE_SUPPORT_URL")).not.toBeInTheDocument();
    expect(screen.queryByText(/supporter licence/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/feature limits/i)).not.toBeInTheDocument();
  });

  it("hides the Support settings destination in production when the support URL is missing or invalid", async () => {
    await renderSettingsWithSupportConfig(operatorMe, {
      showCard: false,
      showPlaceholder: false,
      supportUrl: null,
    });

    expect(
      screen.queryByRole("tab", { name: "Support" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("suite-settings-support"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Support MediaMop" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("VITE_SUPPORT_URL")).not.toBeInTheDocument();
    expect(screen.queryByText(/supporter licence/i)).not.toBeInTheDocument();
  });

  it("hides save for viewers", () => {
    renderSettings(viewerMe);
    expect(screen.getByTestId("suite-settings-save-timezone")).toBeDisabled();
    expect(screen.getByTestId("suite-settings-save-logs")).toBeDisabled();
  });

  it("shows configuration backup + export for operators", () => {
    renderSettings(operatorMe);
    fireEvent.click(screen.getByRole("tab", { name: "Backup and restore" }));
    expect(screen.getByTestId("suite-settings-backup-restore")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Download configuration now" }),
    ).toBeEnabled();
    expect(
      screen.getByRole("button", { name: "Restore from file..." }),
    ).toBeEnabled();
    expect(
      screen.getByRole("button", { name: "Save backup schedule" }),
    ).toBeDisabled();
    expect(
      screen.queryByTestId("suite-settings-history-reset"),
    ).not.toBeInTheDocument();
  });

  it("allows changing and saving backup schedule more than once", async () => {
    let currentSavedSettings: SuiteSettingsOut = {
      ...minimalSuiteSettings,
      configuration_backup_enabled: true,
      configuration_backup_interval_hours: 24,
      configuration_backup_preferred_time: "02:00",
    };
    vi.spyOn(suiteSettingsApi, "fetchSuiteSettings").mockImplementation(
      async () => currentSavedSettings,
    );
    const putSuiteSettingsSpy = vi
      .spyOn(suiteSettingsApi, "putSuiteSettings")
      .mockImplementation(async (body) => {
        currentSavedSettings = {
          ...currentSavedSettings,
          configuration_backup_enabled:
            body.configuration_backup_enabled ?? false,
          configuration_backup_interval_hours:
            body.configuration_backup_interval_hours ?? 24,
          configuration_backup_preferred_time:
            body.configuration_backup_preferred_time ?? "02:00",
          updated_at: "2026-04-12T00:00:00Z",
        };
        return currentSavedSettings;
      });

    renderSettings(operatorMe);
    fireEvent.click(screen.getByRole("tab", { name: "Backup and restore" }));

    fireEvent.change(screen.getByLabelText("Minimum time between runs"), {
      target: { value: "12" },
    });
    fireEvent.change(screen.getByLabelText("Preferred backup time"), {
      target: { value: "03:30" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Save backup schedule" }),
    );

    await waitFor(() => {
      expect(putSuiteSettingsSpy).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Save backup schedule" }),
      ).toBeDisabled();
    });

    fireEvent.change(screen.getByLabelText("Minimum time between runs"), {
      target: { value: "24" },
    });
    fireEvent.change(screen.getByLabelText("Preferred backup time"), {
      target: { value: "04:15" },
    });

    const saveButton = screen.getByRole("button", {
      name: "Save backup schedule",
    });
    expect(saveButton).toBeEnabled();
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(putSuiteSettingsSpy).toHaveBeenCalledTimes(2);
    });
    expect(putSuiteSettingsSpy.mock.calls[1]?.[0]).toMatchObject({
      configuration_backup_interval_hours: 24,
      configuration_backup_preferred_time: "04:15",
    });
  });

  it("hides configuration backup for viewers", () => {
    renderSettings(viewerMe);
    fireEvent.click(screen.getByRole("tab", { name: "Backup and restore" }));
    expect(
      screen.queryByTestId("suite-settings-backup-restore"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("suite-settings-history-reset"),
    ).not.toBeInTheDocument();
  });

  it("keeps General focused and splits Logs, Backup, and Upgrade to their own tabs", () => {
    renderSettings(operatorMe);
    expect(screen.queryByText("Product name")).not.toBeInTheDocument();
    expect(screen.queryByText("Application logs")).not.toBeInTheDocument();
    expect(screen.getByText("Timezone")).toBeInTheDocument();
    expect(screen.getByText("Setup wizard")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "General" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByText("System log retention (days)")).toBeInTheDocument();
    expect(
      screen.getByText(/activity history is kept until you reset it/i),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("suite-settings-history-reset"),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("suite-settings-backup-restore"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("suite-settings-upgrade"),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Backup and restore" }));
    expect(screen.getByTestId("suite-settings-backup-tab")).toBeInTheDocument();
    expect(
      screen.getByTestId("suite-settings-backup-restore"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("System log retention (days)"),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Upgrade" }));
    expect(
      screen.getByTestId("suite-settings-upgrade-tab"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("suite-settings-upgrade")).toBeInTheDocument();
    expect(
      screen.queryByText("System log retention (days)"),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Logs" }));
    expect(screen.getByText("Search logs")).toBeInTheDocument();
    expect(screen.getByText("System events")).toBeInTheDocument();
    expect(screen.getByText("Server diagnostics")).toBeInTheDocument();
    expect(
      screen.queryByText("System log retention (days)"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("Optional home dashboard notice"),
    ).not.toBeInTheDocument();
  });

  it("keeps Upgrade selected when the URL tab query is upgrade", () => {
    renderSettings(operatorMe, {
      updateStatus: windowsUpdateAvailableStatus,
      initialEntries: ["/settings?tab=upgrade"],
    });

    expect(screen.getByRole("tab", { name: "Upgrade" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(
      screen.getByTestId("suite-settings-upgrade-tab"),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("suite-settings-global"),
    ).not.toBeInTheDocument();
  });

  it("shows one-time admin bootstrap guidance when Windows updater service is not ready", () => {
    renderSettings(operatorMe, {
      updateStatus: {
        ...minimalUpdateStatus,
        install_type: "windows",
        in_app_upgrade_supported: false,
        in_app_upgrade_summary:
          "This Windows install does not have the MediaMop updater service yet. Remote in-app upgrade is not available until one newer installer has been run locally as administrator.",
      },
    });
    fireEvent.click(screen.getByRole("tab", { name: "Upgrade" }));
    expect(screen.getByText("One-time setup required")).toBeInTheDocument();
    expect(
      screen.getByText(/run the latest mediamop installer once/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/future upgrades can start remotely from this page/i),
    ).toBeInTheDocument();
  });

  it("does not show one-time bootstrap guidance when updater service is installed but unreachable", () => {
    renderSettings(operatorMe, {
      updateStatus: {
        ...minimalUpdateStatus,
        install_type: "windows",
        status: "update_available",
        in_app_upgrade_supported: false,
        in_app_upgrade_summary:
          "Remote in-app upgrade is unavailable because MediaMop could not reach the local updater service. Ensure the MediaMop Updater service is running on this computer, then click Check again.",
      },
    });
    fireEvent.click(screen.getByRole("tab", { name: "Upgrade" }));
    expect(
      screen.queryByText("One-time setup required"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/could not reach the local updater service/i),
    ).toBeInTheDocument();
  });

  it("shows reconnecting state instead of blind refresh during upgrade polling disconnects", async () => {
    vi.spyOn(suiteSettingsApi, "startSuiteUpdateNow").mockResolvedValue({
      status: "started",
      message:
        "Upgrade request accepted. MediaMop is checking release metadata.",
      attempt_id: "attempt-123",
      target_version: "2.0.8",
      log_path: "C:/ProgramData/MediaMop/upgrades/updater-service.log",
    });
    vi.spyOn(suiteSettingsApi, "fetchSuiteUpdateStatus").mockRejectedValue(
      new Error("network down"),
    );

    renderSettings(operatorMe, { updateStatus: windowsUpdateAvailableStatus });
    fireEvent.click(screen.getByRole("tab", { name: "Upgrade" }));
    fireEvent.click(screen.getByRole("button", { name: "Upgrade now" }));

    await waitFor(() => {
      expect(screen.getByText("Reconnecting")).toBeInTheDocument();
      expect(
        screen.getByText(
          "MediaMop is reconnecting and verifying the installed version.",
        ),
      ).toBeInTheDocument();
    });
  });

  it("treats update-now as accepted work, not completed success", async () => {
    vi.spyOn(suiteSettingsApi, "startSuiteUpdateNow").mockResolvedValue({
      status: "started",
      message:
        "Upgrade request accepted. MediaMop is checking release metadata.",
      attempt_id: "attempt-123",
      target_version: "2.0.8",
      log_path: "C:/ProgramData/MediaMop/upgrades/updater-service.log",
    });
    vi.spyOn(suiteSettingsApi, "fetchSuiteUpdateStatus").mockResolvedValue({
      ...windowsUpdateAvailableStatus,
      upgrade: upgradeProgress({
        phase: "downloading",
        message:
          "Upgrade request accepted. MediaMop is downloading the installer.",
        attempt_id: "attempt-123",
        target_version: "2.0.8",
      }),
    });

    renderSettings(operatorMe, { updateStatus: windowsUpdateAvailableStatus });
    fireEvent.click(screen.getByRole("tab", { name: "Upgrade" }));
    fireEvent.click(screen.getByRole("button", { name: "Upgrade now" }));

    await waitFor(() => {
      expect(screen.getByText("Downloading")).toBeInTheDocument();
      expect(
        screen.getByText(
          "Upgrade request accepted. MediaMop is downloading the installer.",
        ),
      ).toBeInTheDocument();
    });
    expect(
      screen.queryByText(/Upgrade completed\. Running version:/i),
    ).not.toBeInTheDocument();
  });

  it("shows the verifying installer phase from real progress", () => {
    renderSettings(operatorMe, {
      updateStatus: {
        ...windowsUpdateAvailableStatus,
        upgrade: upgradeProgress({
          phase: "verifying_download",
          message: "Installer is being verified.",
          attempt_id: "attempt-123",
          target_version: "2.0.8",
        }),
      },
    });
    fireEvent.click(screen.getByRole("tab", { name: "Upgrade" }));
    expect(screen.getByText("Verifying installer")).toBeInTheDocument();
    expect(
      screen.getByText("Installer is being verified."),
    ).toBeInTheDocument();
  });

  it("shows the installer running phase from real progress", () => {
    renderSettings(operatorMe, {
      updateStatus: {
        ...windowsUpdateAvailableStatus,
        upgrade: upgradeProgress({
          phase: "installer_running",
          message: "Installer is running. MediaMop may temporarily disconnect.",
          attempt_id: "attempt-123",
          target_version: "2.0.8",
        }),
      },
    });
    fireEvent.click(screen.getByRole("tab", { name: "Upgrade" }));
    expect(screen.getByText("Installer running")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Installer is running. MediaMop may temporarily disconnect.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("installer_running")).not.toBeInTheDocument();
    expect(screen.queryByText(/^Phase:/)).not.toBeInTheDocument();
  });

  it("keeps the refresh button stable while upgrade polling is active", () => {
    renderSettings(operatorMe, {
      updateStatus: {
        ...windowsUpdateAvailableStatus,
        upgrade: upgradeProgress({
          phase: "installer_running",
          message: "Installer is running. MediaMop may temporarily disconnect.",
          attempt_id: "attempt-123",
          target_version: "2.0.8",
        }),
      },
    });
    fireEvent.click(screen.getByRole("tab", { name: "Upgrade" }));
    expect(
      screen.getByRole("button", { name: "Checking progress..." }),
    ).toBeDisabled();
    expect(
      screen.queryByRole("button", { name: "Check again" }),
    ).not.toBeInTheDocument();
  });

  it("keeps the refresh button label stable while refetching with stable status data", async () => {
    vi.spyOn(suiteSettingsApi, "fetchSuiteUpdateStatus").mockImplementation(
      () => new Promise(() => {}),
    );
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 0 } },
    });
    qc.setQueryData(suiteSettingsQueryKey, minimalSuiteSettings);
    qc.setQueryData(suiteSecurityOverviewQueryKey, minimalSecurity);
    qc.setQueryData(qk.me, operatorMe);
    qc.setQueryData(qk.session, minimalCurrentSession);
    qc.setQueryData(suiteConfigurationBackupsQueryKey, {
      directory: "C:/MediaMop/backups/suite-configuration",
      items: [],
    });
    qc.setQueryData(suiteUpdateStatusQueryKey, windowsUpdateAvailableStatus);
    qc.setQueryData(
      [
        ...suiteLogsQueryKey,
        {
          level: undefined,
          search: undefined,
          has_exception: undefined,
          limit: 100,
        },
      ],
      minimalLogs,
    );
    qc.setQueryData(suiteMetricsQueryKey, minimalMetrics);

    render(wrap(<SettingsPage />, qc));
    fireEvent.click(screen.getByRole("tab", { name: "Upgrade" }));
    fireEvent.click(screen.getByRole("button", { name: "Check again" }));

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Check again" }),
      ).toBeDisabled();
    });
    expect(
      screen.queryByRole("button", { name: "Checking..." }),
    ).not.toBeInTheDocument();
  });

  it("shows updater diagnostics details when expanded", async () => {
    const diagnostics: SuiteUpdateDiagnosticsOut = {
      current_version: "2.2.0",
      latest_version: "2.2.2",
      install_type: "windows",
      install_root: "C:/Program Files/MediaMop",
      runtime_home: "C:/ProgramData/MediaMop",
      updater_service_reachable: true,
      updater_token_path_present: true,
      installer_log_path:
        "C:/ProgramData/MediaMop/upgrades/installer-attempt-123.log",
      service_log_path: "C:/ProgramData/MediaMop/upgrades/updater-service.log",
      installer_log_tail: ["installer line 1"],
      service_log_tail: ["service line 1"],
      running_processes: [],
      installed_files: [],
      upgrade: null,
    };
    vi.spyOn(suiteSettingsApi, "fetchSuiteUpdateDiagnostics").mockResolvedValue(
      diagnostics,
    );
    renderSettings(operatorMe, { updateStatus: windowsUpdateAvailableStatus });
    fireEvent.click(screen.getByRole("tab", { name: "Upgrade" }));
    fireEvent.click(screen.getByRole("button", { name: "Show diagnostics" }));

    await waitFor(() => {
      expect(
        screen.getByText("Updater service reachable: Yes"),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByText(
        "Installer log: C:/ProgramData/MediaMop/upgrades/installer-attempt-123.log",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Open full updater diagnostics" }),
    ).toHaveAttribute("href", "/api/v1/suite/update-diagnostics");
  });

  it("records and renders upgrade history entries for operator review", () => {
    renderSettings(operatorMe, {
      updateStatus: {
        ...windowsUpdateAvailableStatus,
        upgrade: upgradeProgress({
          phase: "downloading",
          message:
            "Upgrade request accepted. MediaMop is downloading the installer.",
          attempt_id: "attempt-history-1",
          target_version: "2.0.8",
          current_version_seen: "2.0.7",
          last_updated_at: "2026-05-09T03:27:56Z",
        }),
      },
    });
    fireEvent.click(screen.getByRole("tab", { name: "Upgrade" }));
    fireEvent.click(screen.getByRole("button", { name: "Show history" }));
    expect(screen.getByText("Downloading - downloading")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Upgrade request accepted. MediaMop is downloading the installer.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText("Attempt ID: attempt-history-1").length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Target: 2.0.8")).toBeInTheDocument();
  });

  it("does not render a stale old upgrade state as active when a newer release is available", () => {
    renderSettings(operatorMe, {
      updateStatus: {
        ...windowsUpdateAvailableStatus,
        current_version: "2.1.0",
        latest_version: "2.1.2",
        latest_name: "MediaMop 2.1.2",
        summary: "MediaMop 2.1.2 is available.",
        upgrade: upgradeProgress({
          phase: "completed",
          raw_phase: "installer_running",
          message: "Upgrade completed. Running version: 2.1.0.",
          is_active: false,
          is_stale: true,
          blocks_new_update: false,
          stale_reason:
            "Persisted updater state could not prove the original installer process was still active.",
          target_version: "2.1.0",
          current_version_seen: "2.1.0",
        }),
      },
    });
    fireEvent.click(screen.getByRole("tab", { name: "Upgrade" }));

    expect(
      screen.getByRole("button", { name: "Upgrade now" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Installer running")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Upgrade completed. Running version: 2.1.0."),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("installer_running")).not.toBeInTheDocument();
  });

  it("does not treat completed phase as success until the running version matches the target", () => {
    renderSettings(operatorMe, {
      updateStatus: {
        ...windowsUpdateAvailableStatus,
        upgrade: upgradeProgress({
          phase: "completed",
          message: "Upgrade completed. Running version: 2.0.8.",
          target_version: "2.0.8",
          installer_log_path:
            "C:/ProgramData/MediaMop/upgrades/installer-attempt-123.log",
        }),
      },
    });
    fireEvent.click(screen.getByRole("tab", { name: "Upgrade" }));
    expect(screen.getByText("Verifying installed version")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Upgrade reported completed, but the running version has not been confirmed yet.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("Completed")).not.toBeInTheDocument();
  });

  it("shows completed only after the running version matches the target", () => {
    renderSettings(operatorMe, {
      updateStatus: {
        ...windowsUpdateAvailableStatus,
        current_version: "2.0.8",
        status: "up_to_date",
        summary: "This install is already on MediaMop 2.0.8.",
        upgrade: upgradeProgress({
          phase: "completed",
          message: "Upgrade completed. Running version: 2.0.8.",
          target_version: "2.0.8",
          installer_log_path:
            "C:/ProgramData/MediaMop/upgrades/installer-attempt-123.log",
          service_log_path:
            "C:/ProgramData/MediaMop/upgrades/updater-service.log",
        }),
      },
    });
    fireEvent.click(screen.getByRole("tab", { name: "Upgrade" }));
    expect(
      screen.getByText("Upgrade completed. Running version: 2.0.8."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Reload now" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Reload to continue in the updated session."),
    ).toBeInTheDocument();
  });

  it("does not show the refresh browser prompt before the running version matches the target", () => {
    renderSettings(operatorMe, {
      updateStatus: {
        ...windowsUpdateAvailableStatus,
        upgrade: upgradeProgress({
          phase: "completed",
          message: "Upgrade completed. Running version: 2.0.8.",
          target_version: "2.0.8",
        }),
      },
    });
    fireEvent.click(screen.getByRole("tab", { name: "Upgrade" }));
    expect(
      screen.queryByRole("button", { name: "Reload now" }),
    ).not.toBeInTheDocument();
  });

  it("lets the user manually refresh the browser from the completed upgrade state", () => {
    const reloadSpy = vi
      .spyOn(browserWindow, "reloadCurrentPage")
      .mockImplementation(() => undefined);
    renderSettings(operatorMe, {
      updateStatus: {
        ...windowsUpdateAvailableStatus,
        current_version: "2.0.8",
        status: "up_to_date",
        summary: "This install is already on MediaMop 2.0.8.",
        upgrade: upgradeProgress({
          phase: "completed",
          message: "Upgrade completed. Running version: 2.0.8.",
          target_version: "2.0.8",
        }),
      },
    });
    fireEvent.click(screen.getByRole("tab", { name: "Upgrade" }));
    fireEvent.click(screen.getByRole("button", { name: "Reload now" }));
    expect(reloadSpy).toHaveBeenCalledTimes(1);
  });

  it("does not auto-refresh the browser when upgrade verification completes", () => {
    const reloadSpy = vi
      .spyOn(browserWindow, "reloadCurrentPage")
      .mockImplementation(() => undefined);
    renderSettings(operatorMe, {
      updateStatus: {
        ...windowsUpdateAvailableStatus,
        current_version: "2.0.8",
        status: "up_to_date",
        summary: "This install is already on MediaMop 2.0.8.",
        upgrade: upgradeProgress({
          phase: "completed",
          message: "Upgrade completed. Running version: 2.0.8.",
          target_version: "2.0.8",
        }),
      },
    });
    fireEvent.click(screen.getByRole("tab", { name: "Upgrade" }));
    expect(reloadSpy).not.toHaveBeenCalled();
  });

  it("computes a refresh key only after a verified Windows upgrade completes", () => {
    expect(
      verifiedUpgradeRefreshKey(
        {
          ...windowsUpdateAvailableStatus,
          current_version: "2.0.8",
          status: "up_to_date",
          summary: "This install is already on MediaMop 2.0.8.",
        },
        upgradeProgress({
          phase: "completed",
          message: "Upgrade completed. Running version: 2.0.8.",
          attempt_id: "attempt-verified",
          target_version: "2.0.8",
          current_version_seen: "2.0.8",
        }),
        {
          attemptId: "attempt-verified",
          targetVersion: "2.0.8",
          disconnects: 0,
          active: true,
          startedAtMs: Date.now(),
          timedOutReason: null,
        },
      ),
    ).toBe("attempt-verified:2.0.8");
  });

  it("does not compute a refresh key before the running version matches the verified target", () => {
    expect(
      verifiedUpgradeRefreshKey(
        windowsUpdateAvailableStatus,
        upgradeProgress({
          phase: "completed",
          message: "Upgrade completed. Running version: 2.0.8.",
          attempt_id: "attempt-unverified",
          target_version: "2.0.8",
          current_version_seen: "2.0.7",
        }),
        {
          attemptId: "attempt-unverified",
          targetVersion: "2.0.8",
          disconnects: 0,
          active: true,
          startedAtMs: Date.now(),
          timedOutReason: null,
        },
      ),
    ).toBeNull();
  });

  it("shows failed upgrade diagnostics with log paths", () => {
    renderSettings(operatorMe, {
      updateStatus: {
        ...windowsUpdateAvailableStatus,
        upgrade: upgradeProgress({
          phase: "failed",
          message: "Upgrade failed.",
          target_version: "2.0.8",
          last_error: "Running backend still reports 2.0.7 instead of 2.0.8.",
          installer_log_path:
            "C:/ProgramData/MediaMop/upgrades/installer-attempt-123.log",
          service_log_path:
            "C:/ProgramData/MediaMop/upgrades/updater-service.log",
        }),
      },
    });
    fireEvent.click(screen.getByRole("tab", { name: "Upgrade" }));
    expect(
      screen.getByText(
        "Upgrade failed: Running backend still reports 2.0.7 instead of 2.0.8.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Installer log: C:/ProgramData/MediaMop/upgrades/installer-attempt-123.log",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Service log: C:/ProgramData/MediaMop/upgrades/updater-service.log",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Open updater diagnostics" }),
    ).toHaveAttribute("href", "/api/v1/suite/update-diagnostics");
  });

  it("fails the upgrade UI when version verification times out with the old version still running", () => {
    renderSettings(operatorMe, {
      updateStatus: {
        ...windowsUpdateAvailableStatus,
        upgrade: upgradeProgress({
          phase: "verifying_install",
          message:
            "MediaMop is reconnecting and verifying the installed version.",
          attempt_id: "attempt-123",
          target_version: "2.0.8",
          current_version_seen: "2.0.7",
          last_started_at: new Date(Date.now() - 9 * 60 * 1000).toISOString(),
          installer_log_path:
            "C:/ProgramData/MediaMop/upgrades/installer-attempt-123.log",
          service_log_path:
            "C:/ProgramData/MediaMop/upgrades/updater-service.log",
        }),
      },
    });
    fireEvent.click(screen.getByRole("tab", { name: "Upgrade" }));
    expect(
      screen.getAllByText(
        "Upgrade failed: MediaMop did not verify version 2.0.8 within 8 minutes. The running app still reports 2.0.7.",
      ),
    ).toHaveLength(2);
    expect(screen.getByText("Status: Failed")).toBeInTheDocument();
    expect(screen.getByText("Attempt ID: attempt-123")).toBeInTheDocument();
    expect(screen.getByText("Current version seen: 2.0.7")).toBeInTheDocument();
  });

  it("does not render mojibake in the upgrade panel", () => {
    renderSettings(operatorMe, { updateStatus: windowsUpdateAvailableStatus });
    fireEvent.click(screen.getByRole("tab", { name: "Upgrade" }));

    expect(document.body.textContent).not.toContain("â");
    expect(document.body.textContent).not.toContain("Ã");
    expect(document.body.textContent).not.toContain("�");
  });

  it("shows change password only on Security tab", () => {
    renderSettings(operatorMe);
    fireEvent.click(screen.getByRole("tab", { name: "Security" }));
    expect(
      screen.getByRole("heading", { name: "Change password" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Security posture" }),
    ).not.toBeInTheDocument();
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
    expect(screen.getByRole("button", { name: /Timezone/ })).toHaveTextContent(
      chosenLabel,
    );
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
    expect(document.documentElement.getAttribute("data-mm-density")).toBe(
      "comfortable",
    );
    fireEvent.click(screen.getByText("Expanded"));
    expect(document.documentElement.getAttribute("data-mm-density")).toBe(
      "expanded",
    );
    fireEvent.click(screen.getByText("Balanced"));
    expect(document.documentElement.getAttribute("data-mm-density")).toBeNull();
  });
});
