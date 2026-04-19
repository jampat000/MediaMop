import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as fetcherOverviewStatsApi from "../../lib/fetcher/overview-stats-api";
import { qk } from "../../lib/auth/queries";
import type { UserPublic } from "../../lib/api/types";
import type {
  FetcherFailedImportAutomationSummary,
  FetcherFailedImportQueueAttentionSnapshot,
} from "../../lib/fetcher/failed-imports/types";
import {
  failedImportAutomationSummaryQueryKey,
  failedImportCleanupPolicyQueryKey,
  failedImportQueueAttentionSnapshotQueryKey,
  failedImportSettingsQueryKey,
} from "../../lib/fetcher/failed-imports/queries";
import type { FetcherFailedImportCleanupPolicyOut } from "../../lib/fetcher/failed-imports/types";
import { fetcherArrOperatorSettingsQueryKey } from "../../lib/fetcher/arr-operator-settings/queries";
import { fetcherOverviewStatsQueryKey } from "../../lib/fetcher/queries";
import type {
  FetcherArrConnectionPanel,
  FetcherArrOperatorSettingsOut,
} from "../../lib/fetcher/arr-operator-settings/types";
import { fetcherJobsInspectionQueryKey } from "../../lib/fetcher/jobs-inspection/queries";
import { MM_SCHEDULE_TIME_WINDOW_HELPER } from "../../components/ui/mm-schedule-window-controls";
import { FETCHER_TAB_RADARR_LABEL, FETCHER_TAB_SONARR_LABEL } from "./fetcher-display-names";
import { FetcherPage } from "./fetcher-page";

function wrap(ui: ReactNode, client: QueryClient) {
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

const minimalMe: UserPublic = { id: 1, username: "alice", role: "viewer" };

const minimalFiSettings = {
  background_job_worker_count: 0,
  in_process_workers_disabled: true,
  in_process_workers_enabled: false,
  worker_mode_summary: "test",
  failed_import_radarr_cleanup_drive_schedule_enabled: false,
  failed_import_radarr_cleanup_drive_schedule_interval_seconds: 3600,
  failed_import_sonarr_cleanup_drive_schedule_enabled: false,
  failed_import_sonarr_cleanup_drive_schedule_interval_seconds: 3600,
  visibility_note: "note",
};

const lane = (enabled: boolean) => ({
  enabled,
  max_items_per_run: 50,
  retry_delay_minutes: 1440,
  schedule_enabled: false,
  schedule_days: "",
  schedule_start: "00:00",
  schedule_end: "23:59",
  schedule_interval_seconds: 3600,
});

const minimalConnectionPanel = (overrides: Partial<FetcherArrConnectionPanel> = {}): FetcherArrConnectionPanel => ({
  enabled: false,
  base_url: "",
  api_key_is_saved: false,
  last_test_ok: null,
  last_test_at: null,
  last_test_detail: null,
  status_headline: "Connection status: Not checked yet",
  effective_base_url: null,
  ...overrides,
});

const minimalArrOperatorSettings: FetcherArrOperatorSettingsOut = {
  sonarr_missing: lane(false),
  sonarr_upgrade: lane(false),
  radarr_missing: lane(false),
  radarr_upgrade: lane(false),
  sonarr_connection: minimalConnectionPanel(),
  radarr_connection: minimalConnectionPanel(),
  schedule_timezone: "UTC",
  connection_note: "Addresses come from the server file.",
  interval_restart_note: "Restart note.",
  sonarr_server_configured: false,
  radarr_server_configured: false,
  sonarr_server_url: null,
  radarr_server_url: null,
  updated_at: "2026-04-11T12:00:00Z",
};

const minimalQueueAttention: FetcherFailedImportQueueAttentionSnapshot = {
  tv_shows: { needs_attention_count: 0, last_checked_at: null },
  movies: { needs_attention_count: 0, last_checked_at: null },
};

const axisCleanupAllOff = {
  handling_quality_rejection: "leave_alone" as const,
  handling_unmatched_manual_import: "leave_alone" as const,
  handling_sample_release: "leave_alone" as const,
  handling_corrupt_import: "leave_alone" as const,
  handling_failed_download: "leave_alone" as const,
  handling_failed_import: "leave_alone" as const,
  cleanup_drive_schedule_enabled: false,
  cleanup_drive_schedule_interval_seconds: 3600,
};

const minimalCleanupPolicy: FetcherFailedImportCleanupPolicyOut = {
  movies: { ...axisCleanupAllOff },
  tv_shows: { ...axisCleanupAllOff },
  updated_at: "2026-04-11T12:00:00Z",
};

const minimalAutomationSummary: FetcherFailedImportAutomationSummary = {
  scope_note: "From finished passes and saved settings in this app only.",
  automation_slots_note: "Automation slots are set to 0 — timed passes will not start by themselves.",
  movies: {
    last_finished_at: null,
    last_outcome_label: "No finished movie pass recorded yet.",
    saved_schedule_primary: "Saved schedule: timed sweep off",
    saved_schedule_secondary: null,
  },
  tv_shows: {
    last_finished_at: "2026-04-11T12:00:00Z",
    last_outcome_label: "Completed",
    saved_schedule_primary: "Saved schedule: timed sweep off",
    saved_schedule_secondary: null,
  },
};

function renderFetcherPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(qk.me, minimalMe);
  qc.setQueryData(failedImportSettingsQueryKey, minimalFiSettings);
  qc.setQueryData(failedImportAutomationSummaryQueryKey, minimalAutomationSummary);
  qc.setQueryData(failedImportQueueAttentionSnapshotQueryKey, minimalQueueAttention);
  qc.setQueryData(failedImportCleanupPolicyQueryKey, minimalCleanupPolicy);
  qc.setQueryData(fetcherJobsInspectionQueryKey("terminal"), { jobs: [], default_terminal_only: true });
  qc.setQueryData(fetcherArrOperatorSettingsQueryKey, minimalArrOperatorSettings);
  qc.setQueryData(fetcherOverviewStatsQueryKey, {
    window_days: 30,
    sonarr_missing_searches: 0,
    sonarr_upgrade_searches: 0,
    radarr_missing_searches: 0,
    radarr_upgrade_searches: 0,
    total_searches: 0,
    failed_jobs: 0,
  });
  return { qc, ...render(wrap(<FetcherPage />, qc)) };
}

function overviewSectionOrders(panel: HTMLElement): string[] {
  return Array.from(panel.querySelectorAll("[data-overview-order]")).map((el) => el.getAttribute("data-overview-order") ?? "");
}

describe("FetcherPage (tabbed IA)", () => {
  beforeEach(() => {
    vi.spyOn(fetcherOverviewStatsApi, "fetchFetcherOverviewStats").mockResolvedValue({
      window_days: 30,
      sonarr_missing_searches: 0,
      sonarr_upgrade_searches: 0,
      radarr_missing_searches: 0,
      radarr_upgrade_searches: 0,
      total_searches: 0,
      failed_jobs: 0,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("defaults to Overview with the three-section landing path, not the failed-import workspace", () => {
    renderFetcherPage();
    expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByTestId("fetcher-failed-imports-workspace")).not.toBeInTheDocument();
    const panel = screen.getByTestId("fetcher-overview-panel");
    expect(overviewSectionOrders(panel)).toEqual(["1", "2", "3"]);
    expect(screen.getByTestId("fetcher-overview-at-a-glance")).toBeInTheDocument();
    expect(screen.getByTestId("fetcher-overview-needs-attention")).toBeInTheDocument();
    expect(screen.getByTestId("fetcher-overview-next-steps")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Next steps" })).toBeInTheDocument();
    expect(screen.queryByTestId("fetcher-automation-summary")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Current search setup" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("fetcher-overview-fi-needs-attention")).not.toBeInTheDocument();
    const glance = screen.getByTestId("fetcher-overview-at-a-glance");
    expect(glance.textContent ?? "").toMatch(/Sonarr \(TV\):/i);
    expect(glance.textContent ?? "").toMatch(/All leave alone/i);
    expect(glance.textContent ?? "").toMatch(/No items need attention/i);
    expect(screen.queryByTestId("fetcher-overview-fi-preview")).not.toBeInTheDocument();
    expect(screen.queryByTestId("fetcher-overview-connections-service")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Download queue preview" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Connections & optional service link" })).not.toBeInTheDocument();
  });

  it("orders At a glance inner cards: Last 30 days, Connections, Failed imports", () => {
    renderFetcherPage();
    const glance = screen.getByTestId("fetcher-overview-at-a-glance");
    const order = Array.from(glance.querySelectorAll("[data-at-glance-order]")).map(
      (el) => el.getAttribute("data-at-glance-order") ?? "",
    );
    expect(order).toEqual(["1", "2", "3"]);
    const h3 = within(glance).getAllByRole("heading", { level: 3 });
    expect(h3.map((h) => h.textContent)).toEqual(["Last 30 days", "Connections", "Failed imports"]);
  });

  it("summarizes At a glance failed imports from saved cleanup policy (not queue attention)", () => {
    renderFetcherPage();
    const glance = screen.getByTestId("fetcher-overview-at-a-glance");
    const t = glance.textContent ?? "";
    expect(t).toMatch(/Sonarr \(TV\):/i);
    expect(t).toMatch(/Radarr \(Movies\):/i);
    expect(t).toMatch(/All leave alone/i);
  });

  it("lists Sonarr (TV) before Radarr (Movies) in At a glance Failed imports card", () => {
    renderFetcherPage();
    const glance = screen.getByTestId("fetcher-overview-at-a-glance");
    const fiHeading = within(glance).getByRole("heading", { name: "Failed imports" });
    const card = fiHeading.parentElement;
    expect(card).toBeTruthy();
    const t = (card as HTMLElement).textContent ?? "";
    expect(t.indexOf("Sonarr (TV):")).toBeLessThan(t.indexOf("Radarr (Movies):"));
  });

  it("routes Needs attention to Sonarr and Radarr tabs when apps are connected but searches are off", () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(qk.me, minimalMe);
    qc.setQueryData(failedImportSettingsQueryKey, minimalFiSettings);
    qc.setQueryData(failedImportAutomationSummaryQueryKey, minimalAutomationSummary);
    qc.setQueryData(failedImportQueueAttentionSnapshotQueryKey, minimalQueueAttention);
    qc.setQueryData(failedImportCleanupPolicyQueryKey, minimalCleanupPolicy);
    qc.setQueryData(fetcherJobsInspectionQueryKey("terminal"), { jobs: [], default_terminal_only: true });
    qc.setQueryData(fetcherArrOperatorSettingsQueryKey, {
      ...minimalArrOperatorSettings,
      sonarr_server_configured: true,
      radarr_server_configured: true,
    });
    render(wrap(<FetcherPage />, qc));
    expect(screen.getByText("Turn on TV searches or upgrades for Sonarr")).toBeInTheDocument();
    expect(screen.getByText("Turn on movie searches or upgrades for Radarr")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: `Open ${FETCHER_TAB_SONARR_LABEL}` }));
    expect(screen.getByRole("tab", { name: FETCHER_TAB_SONARR_LABEL })).toHaveAttribute("aria-selected", "true");
    fireEvent.click(screen.getByRole("tab", { name: "Overview" }));
    fireEvent.click(screen.getByRole("button", { name: `Open ${FETCHER_TAB_RADARR_LABEL}` }));
    expect(screen.getByRole("tab", { name: FETCHER_TAB_RADARR_LABEL })).toHaveAttribute("aria-selected", "true");
  });

  it("does not embed the full failed-import workspace or the old long service-check dump on Overview", () => {
    renderFetcherPage();
    expect(screen.queryByTestId("fetcher-failed-imports-workspace")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Service checks" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Latest link check" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "How this page is organized" })).not.toBeInTheDocument();
  });

  it("shows failed-import workspace on the Failed imports tab", () => {
    renderFetcherPage();
    fireEvent.click(screen.getByRole("tab", { name: "Failed imports" }));
    expect(screen.getByTestId("fetcher-failed-imports-workspace")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Failed imports" })).toBeInTheDocument();
  });

  it("exposes Connections, Sonarr, Radarr, and Failed imports tabs in locked order after Overview", () => {
    renderFetcherPage();
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((b) => b.textContent)).toEqual([
      "Overview",
      "Connections",
      FETCHER_TAB_SONARR_LABEL,
      FETCHER_TAB_RADARR_LABEL,
      "Failed imports",
    ]);
  });

  it("shows library search settings after opening the Sonarr tab", () => {
    renderFetcherPage();
    fireEvent.click(screen.getByRole("tab", { name: FETCHER_TAB_SONARR_LABEL }));
    expect(screen.getByTestId("fetcher-arr-operator-settings")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: FETCHER_TAB_SONARR_LABEL })).toBeInTheDocument();
    const arrPanel = screen.getByTestId("fetcher-arr-operator-settings");
    expect(arrPanel.textContent).toMatch(/Configure Fetcher search behavior for Sonarr \(TV\)/i);
    expect(within(arrPanel).getByRole("link", { name: "Activity" })).toBeInTheDocument();
  });

  it("shows the full suite timezone label in search schedule preamble", () => {
    const { qc } = renderFetcherPage();
    act(() => {
      qc.setQueryData(fetcherArrOperatorSettingsQueryKey, {
        ...minimalArrOperatorSettings,
        schedule_timezone: "America/New_York",
      });
    });
    fireEvent.click(screen.getByRole("tab", { name: FETCHER_TAB_SONARR_LABEL }));
    expect(screen.getByTestId("fetcher-tv-preamble")).toHaveTextContent("United States — New York");
  });

  it("keeps unsaved lane draft edits after another lane refetch", () => {
    const { qc } = renderFetcherPage();
    fireEvent.click(screen.getByRole("tab", { name: FETCHER_TAB_SONARR_LABEL }));
    const upgradeLane = screen.getByTestId("fetcher-tv-lane-upgrade");
    const upgradeSpinboxes = within(upgradeLane).getAllByRole("spinbutton");
    fireEvent.change(upgradeSpinboxes[1], { target: { value: "123" } });
    expect((upgradeSpinboxes[1] as HTMLInputElement).value).toBe("123");

    const refreshed = {
      ...minimalArrOperatorSettings,
      sonarr_missing: {
        ...minimalArrOperatorSettings.sonarr_missing,
        max_items_per_run: 88,
      },
    };
    act(() => {
      qc.setQueryData(fetcherArrOperatorSettingsQueryKey, refreshed);
    });

    const upgradeSpinboxesAfter = within(screen.getByTestId("fetcher-tv-lane-upgrade")).getAllByRole("spinbutton");
    expect((upgradeSpinboxesAfter[1] as HTMLInputElement).value).toBe("123");
  });

  it("shows side-by-side TV and movie library connection panels on Connections", () => {
    renderFetcherPage();
    fireEvent.click(screen.getByRole("tab", { name: "Connections" }));
    expect(screen.getByTestId("fetcher-connections-panels")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Connections" })).toBeInTheDocument();
    expect(screen.getByText(/Manage Sonarr and Radarr connection state/i)).toBeInTheDocument();
    expect(screen.getByText(/Search timing and limits stay on the/i)).toBeInTheDocument();
    expect(screen.queryByText(/Library link is active/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Library link is paused/i)).not.toBeInTheDocument();
    const grid = screen.getByTestId("fetcher-connection-panels-grid");
    expect(grid).toBeTruthy();
    const panels = grid.querySelectorAll("[data-testid^=\"fetcher-connection-panel-\"]");
    expect(panels.length).toBe(2);
    expect(panels[0].getAttribute("data-testid")).toBe("fetcher-connection-panel-sonarr");
    expect(panels[1].getAttribute("data-testid")).toBe("fetcher-connection-panel-radarr");
    expect(within(panels[0] as HTMLElement).getByRole("heading", { name: "Sonarr" })).toBeInTheDocument();
    expect(within(panels[1] as HTMLElement).getByRole("heading", { name: "Radarr" })).toBeInTheDocument();
    expect(within(panels[0] as HTMLElement).getByRole("button", { name: "Save Sonarr" })).toBeInTheDocument();
    expect(within(panels[0] as HTMLElement).getByRole("button", { name: "Test Sonarr" })).toBeInTheDocument();
    expect(within(panels[1] as HTMLElement).getByRole("button", { name: "Save Radarr" })).toBeInTheDocument();
    expect(within(panels[1] as HTMLElement).getByRole("button", { name: "Test Radarr" })).toBeInTheDocument();
    const sonPanel = panels[0] as HTMLElement;
    const sonHtml = sonPanel.innerHTML;
    const enableIdx = sonHtml.indexOf("Enable / Disable");
    const urlIdx = sonHtml.indexOf("Base URL");
    const keyIdx = sonHtml.indexOf("API key");
    const saveIdx = sonHtml.indexOf("Save Sonarr");
    const testIdx = sonHtml.indexOf("Test Sonarr");
    const statusIdx = sonHtml.indexOf("Connection status:");
    expect(enableIdx).toBeGreaterThanOrEqual(0);
    expect(urlIdx).toBeGreaterThan(enableIdx);
    expect(keyIdx).toBeGreaterThan(urlIdx);
    expect(saveIdx).toBeGreaterThan(keyIdx);
    expect(testIdx).toBeGreaterThan(saveIdx);
    expect(statusIdx).toBeGreaterThan(testIdx);
    expect(screen.getByTestId("fetcher-connection-status-sonarr")).toHaveTextContent(/Connection status: Not checked yet/i);
    expect(within(sonPanel).getByText(/Off:/i)).toBeInTheDocument();
  });

  it("toggles API key visibility on Connections", () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(qk.me, { ...minimalMe, role: "operator" });
    qc.setQueryData(failedImportSettingsQueryKey, minimalFiSettings);
    qc.setQueryData(failedImportAutomationSummaryQueryKey, minimalAutomationSummary);
    qc.setQueryData(failedImportQueueAttentionSnapshotQueryKey, minimalQueueAttention);
    qc.setQueryData(failedImportCleanupPolicyQueryKey, minimalCleanupPolicy);
    qc.setQueryData(fetcherJobsInspectionQueryKey("terminal"), { jobs: [], default_terminal_only: true });
    qc.setQueryData(fetcherArrOperatorSettingsQueryKey, minimalArrOperatorSettings);
    render(wrap(<FetcherPage />, qc));
    fireEvent.click(screen.getByRole("tab", { name: "Connections" }));
    const sonPanel = screen.getByTestId("fetcher-connection-panel-sonarr");
    const keyInput = sonPanel.querySelector("#fetcher-conn-key-sonarr");
    expect(keyInput).toBeTruthy();
    expect(keyInput).toHaveAttribute("type", "password");
    fireEvent.click(within(sonPanel).getByRole("button", { name: "Show" }));
    expect(keyInput).toHaveAttribute("type", "text");
    fireEvent.click(within(sonPanel).getByRole("button", { name: "Hide" }));
    expect(keyInput).toHaveAttribute("type", "password");
  });

  it("uses an empty API key field with a bullet placeholder when a key is saved server-side", () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(qk.me, { ...minimalMe, role: "operator" });
    qc.setQueryData(failedImportSettingsQueryKey, minimalFiSettings);
    qc.setQueryData(failedImportAutomationSummaryQueryKey, minimalAutomationSummary);
    qc.setQueryData(failedImportQueueAttentionSnapshotQueryKey, minimalQueueAttention);
    qc.setQueryData(failedImportCleanupPolicyQueryKey, minimalCleanupPolicy);
    qc.setQueryData(fetcherJobsInspectionQueryKey("terminal"), { jobs: [], default_terminal_only: true });
    qc.setQueryData(fetcherArrOperatorSettingsQueryKey, {
      ...minimalArrOperatorSettings,
      sonarr_connection: minimalConnectionPanel({ api_key_is_saved: true }),
    });
    render(wrap(<FetcherPage />, qc));
    fireEvent.click(screen.getByRole("tab", { name: "Connections" }));
    const sonPanel = screen.getByTestId("fetcher-connection-panel-sonarr");
    const keyInput = sonPanel.querySelector("#fetcher-conn-key-sonarr") as HTMLInputElement;
    expect(keyInput.value).toBe("");
    const ph = keyInput.getAttribute("placeholder");
    expect(ph).toMatch(/^\u2022+$/);
    expect(within(sonPanel).getByRole("button", { name: "Show" })).not.toBeDisabled();
    expect(within(sonPanel).getByText(/Leave blank to keep your saved key/i)).toBeInTheDocument();
  });

  it("hero frames Fetcher as a landing-first flow", () => {
    const { container } = renderFetcherPage();
    const hero = container.querySelector(".mm-page__intro");
    expect(hero).toBeTruthy();
    const t = hero!.textContent ?? "";
    expect(t).toMatch(/Fetcher/i);
    expect(t).toMatch(/missing TV shows and movies/i);
    expect(t).not.toMatch(/Refiner/i);
  });

  it("keeps library search tabs focused on saved lane preferences, not failed-import pass history", () => {
    renderFetcherPage();
    fireEvent.click(screen.getByRole("tab", { name: FETCHER_TAB_SONARR_LABEL }));
    const arrPanel = screen.getByTestId("fetcher-arr-operator-settings");
    const t = arrPanel.textContent ?? "";
    expect(t).toMatch(/Missing TV shows/i);
    expect(t).toMatch(/TV upgrades/i);
    expect(t.toLowerCase()).not.toContain("last finished");
    expect(t.toLowerCase()).not.toContain("last outcome");
  });

  it("shows the server connection note on Connections when the API sends one", () => {
    renderFetcherPage();
    fireEvent.click(screen.getByRole("tab", { name: "Connections" }));
    expect(screen.getByTestId("fetcher-connections-note")).toHaveTextContent("Addresses come from the server file.");
  });

  it("uses per-lane save labels on TV and Movies tabs when the operator can edit", () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(qk.me, { ...minimalMe, role: "operator" });
    qc.setQueryData(failedImportSettingsQueryKey, minimalFiSettings);
    qc.setQueryData(failedImportAutomationSummaryQueryKey, minimalAutomationSummary);
    qc.setQueryData(failedImportQueueAttentionSnapshotQueryKey, minimalQueueAttention);
    qc.setQueryData(failedImportCleanupPolicyQueryKey, minimalCleanupPolicy);
    qc.setQueryData(fetcherJobsInspectionQueryKey("terminal"), { jobs: [], default_terminal_only: true });
    qc.setQueryData(fetcherArrOperatorSettingsQueryKey, minimalArrOperatorSettings);
    render(wrap(<FetcherPage />, qc));
    fireEvent.click(screen.getByRole("tab", { name: FETCHER_TAB_SONARR_LABEL }));
    expect(screen.getByRole("button", { name: "Save missing TV show searches" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save TV upgrades" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: FETCHER_TAB_RADARR_LABEL }));
    expect(screen.getByRole("button", { name: "Save missing movie searches" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save movie upgrades" })).toBeInTheDocument();
  });

  it("structures TV (Sonarr) with two bubbles, locked copy, helpers, and control order inside each bubble", () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(qk.me, { ...minimalMe, role: "operator" });
    qc.setQueryData(failedImportSettingsQueryKey, minimalFiSettings);
    qc.setQueryData(failedImportAutomationSummaryQueryKey, minimalAutomationSummary);
    qc.setQueryData(failedImportQueueAttentionSnapshotQueryKey, minimalQueueAttention);
    qc.setQueryData(failedImportCleanupPolicyQueryKey, minimalCleanupPolicy);
    qc.setQueryData(fetcherJobsInspectionQueryKey("terminal"), { jobs: [], default_terminal_only: true });
    qc.setQueryData(fetcherArrOperatorSettingsQueryKey, minimalArrOperatorSettings);
    render(wrap(<FetcherPage />, qc));
    fireEvent.click(screen.getByRole("tab", { name: FETCHER_TAB_SONARR_LABEL }));
    const tvGrid = screen.getByTestId("fetcher-tv-lanes-grid");
    expect(within(tvGrid).getByTestId("fetcher-tv-preamble")).toBeInTheDocument();
    expect(within(tvGrid).getByTestId("fetcher-tv-lane-missing")).toBeInTheDocument();
    expect(within(tvGrid).getByTestId("fetcher-tv-lane-upgrade")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Missing TV shows" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "TV upgrades" })).toBeInTheDocument();
    expect(screen.getByText("Set up searches for missing TV shows.")).toBeInTheDocument();
    expect(screen.getByText("Set up searches for better quality TV episodes.")).toBeInTheDocument();
    expect(screen.getAllByText("How often this search runs automatically.").length).toBe(2);
    expect(screen.getAllByText(MM_SCHEDULE_TIME_WINDOW_HELPER).length).toBe(2);
    expect(screen.getAllByText("How many items this search will look for each time it runs.").length).toBe(2);
    expect(screen.getAllByText("How long to wait before searching the same item again.").length).toBe(2);
    const missing = screen.getByTestId("fetcher-tv-lane-missing");
    const h = missing.innerHTML;
    const idx = (s: string) => h.indexOf(s);
    expect(idx("Enable timed scans")).toBeLessThan(idx("Run interval"));
    expect(idx("Run interval")).toBeLessThan(idx("Time window"));
    expect(idx("Time window")).toBeLessThan(idx("Items per run"));
    expect(idx("Items per run")).toBeLessThan(idx("Retry cooldown"));
    expect(idx("Retry cooldown")).toBeLessThan(idx("Save missing TV show searches"));
  });

  it("mirrors TV structure on Movies (Radarr) with two bubbles and the same helper pattern", () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(qk.me, { ...minimalMe, role: "operator" });
    qc.setQueryData(failedImportSettingsQueryKey, minimalFiSettings);
    qc.setQueryData(failedImportAutomationSummaryQueryKey, minimalAutomationSummary);
    qc.setQueryData(failedImportQueueAttentionSnapshotQueryKey, minimalQueueAttention);
    qc.setQueryData(failedImportCleanupPolicyQueryKey, minimalCleanupPolicy);
    qc.setQueryData(fetcherJobsInspectionQueryKey("terminal"), { jobs: [], default_terminal_only: true });
    qc.setQueryData(fetcherArrOperatorSettingsQueryKey, minimalArrOperatorSettings);
    render(wrap(<FetcherPage />, qc));
    fireEvent.click(screen.getByRole("tab", { name: FETCHER_TAB_RADARR_LABEL }));
    const moviesGrid = screen.getByTestId("fetcher-movies-lanes-grid");
    expect(within(moviesGrid).getByTestId("fetcher-movies-preamble")).toBeInTheDocument();
    expect(within(moviesGrid).getByTestId("fetcher-movies-lane-missing")).toBeInTheDocument();
    expect(within(moviesGrid).getByTestId("fetcher-movies-lane-upgrade")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Missing movies" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Movie upgrades" })).toBeInTheDocument();
    expect(screen.getByText("Set up searches for missing movies.")).toBeInTheDocument();
    expect(screen.getByText("Set up searches for better quality movies.")).toBeInTheDocument();
    expect(screen.getByTestId("fetcher-arr-operator-settings").textContent).toMatch(
      /Configure Fetcher search behavior for Radarr \(Movies\)/i,
    );
    const missing = screen.getByTestId("fetcher-movies-lane-missing");
    const h = missing.innerHTML;
    const idx = (s: string) => h.indexOf(s);
    expect(idx("Enable timed scans")).toBeLessThan(idx("Run interval"));
    expect(idx("Run interval")).toBeLessThan(idx("Time window"));
    expect(idx("Time window")).toBeLessThan(idx("Items per run"));
    expect(idx("Items per run")).toBeLessThan(idx("Retry cooldown"));
    expect(idx("Retry cooldown")).toBeLessThan(idx("Save missing movie searches"));
  });

  it("describes each library tab as its own search-behavior surface", () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(qk.me, { ...minimalMe, role: "operator" });
    qc.setQueryData(failedImportSettingsQueryKey, minimalFiSettings);
    qc.setQueryData(failedImportAutomationSummaryQueryKey, minimalAutomationSummary);
    qc.setQueryData(failedImportQueueAttentionSnapshotQueryKey, minimalQueueAttention);
    qc.setQueryData(failedImportCleanupPolicyQueryKey, minimalCleanupPolicy);
    qc.setQueryData(fetcherJobsInspectionQueryKey("terminal"), { jobs: [], default_terminal_only: true });
    qc.setQueryData(fetcherArrOperatorSettingsQueryKey, minimalArrOperatorSettings);
    render(wrap(<FetcherPage />, qc));
    fireEvent.click(screen.getByRole("tab", { name: FETCHER_TAB_SONARR_LABEL }));
    expect(screen.getByTestId("fetcher-arr-operator-settings").textContent).toMatch(
      /Configure Fetcher search behavior for Sonarr \(TV\)/i,
    );
    fireEvent.click(screen.getByRole("tab", { name: FETCHER_TAB_RADARR_LABEL }));
    expect(screen.getByTestId("fetcher-arr-operator-settings").textContent).toMatch(
      /Configure Fetcher search behavior for Radarr \(Movies\)/i,
    );
  });

  it("opens the Failed imports tab from the main tab row", () => {
    renderFetcherPage();
    fireEvent.click(screen.getByRole("tab", { name: "Failed imports" }));
    expect(screen.getByTestId("fetcher-failed-imports-workspace")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Failed imports" })).toHaveAttribute("aria-selected", "true");
  });
});
