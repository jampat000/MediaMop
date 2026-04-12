import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { qk } from "../../lib/auth/queries";
import type { FetcherOperationalOverview, UserPublic } from "../../lib/api/types";
import type { FetcherFailedImportAutomationSummary } from "../../lib/fetcher/failed-imports/types";
import {
  failedImportAutomationSummaryQueryKey,
  failedImportSettingsQueryKey,
} from "../../lib/fetcher/failed-imports/queries";
import { fetcherJobsInspectionQueryKey } from "../../lib/fetcher/jobs-inspection/queries";
import { fetcherOverviewKey } from "../../lib/fetcher/queries";
import { FetcherPage } from "./fetcher-page";

function wrap(ui: ReactNode, client: QueryClient) {
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

const minimalMe: UserPublic = { id: 1, username: "alice", role: "viewer" };

const minimalOverview: FetcherOperationalOverview = {
  mediamop_version: "test",
  status_label: "ok",
  status_detail: "fine",
  connection: {
    configured: false,
    target_display: null,
    reachable: null,
    http_status: null,
    latency_ms: null,
    fetcher_app: null,
    fetcher_version: null,
    detail: null,
  },
  probe_persisted_24h: { window_hours: 24, persisted_ok: 0, persisted_failed: 0 },
  probe_failure_window_days: 7,
  recent_probe_failures: [],
  latest_probe_event: null,
  recent_probe_events: [],
};

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
  qc.setQueryData(fetcherOverviewKey, minimalOverview);
  qc.setQueryData(failedImportSettingsQueryKey, minimalFiSettings);
  qc.setQueryData(failedImportAutomationSummaryQueryKey, minimalAutomationSummary);
  qc.setQueryData(fetcherJobsInspectionQueryKey("terminal"), { jobs: [], default_terminal_only: true });
  return render(wrap(<FetcherPage />, qc));
}

describe("FetcherPage (hero compression)", () => {
  it("places failed-import workspace with a plain section title", () => {
    renderFetcherPage();
    expect(screen.getByTestId("fetcher-failed-imports-workspace")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Failed imports" })).toBeInTheDocument();
  });

  it("hero frames the whole module: failed imports plus service checks, not a subsection alone", () => {
    const { container } = renderFetcherPage();
    const hero = container.querySelector(".mm-page__intro");
    expect(hero).toBeTruthy();
    const t = hero!.textContent ?? "";
    expect(t).toMatch(/Fetcher/i);
    expect(t).toMatch(/Radarr/i);
    expect(t).toMatch(/Sonarr/i);
    expect(t).toMatch(/failed-import|failed import/i);
    expect(t).toMatch(/Arr|search/i);
    expect(t).toMatch(/service|answered|checks/i);
    expect(t).not.toMatch(/Refiner/i);
  });

  it("second block is compressed service checks, not architecture titles", () => {
    renderFetcherPage();
    expect(screen.getByRole("heading", { name: "Service checks" })).toBeInTheDocument();
    expect(screen.queryByText(/External Fetcher application/i)).toBeNull();
    expect(screen.queryByText(/MEDIAMOP_FETCHER_BASE_URL/i)).toBeNull();
  });

  it("shows read-only automation summary for movies and TV with no fake liveness copy", () => {
    const { container } = renderFetcherPage();
    expect(screen.getByTestId("fetcher-automation-summary")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Failed-import automation summary" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Movies" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "TV shows" })).toBeInTheDocument();
    const t = container.textContent ?? "";
    expect(t.toLowerCase()).not.toContain("healthy");
    expect(t.toLowerCase()).not.toContain("live ok");
    expect(t.toLowerCase()).not.toContain("reachable");
  });
});
