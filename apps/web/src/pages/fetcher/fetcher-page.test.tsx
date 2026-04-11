import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { qk } from "../../lib/auth/queries";
import type { FetcherOperationalOverview, UserPublic } from "../../lib/api/types";
import {
  failedImportInspectionQueryKey,
  failedImportSettingsQueryKey,
} from "../../lib/fetcher/failed-imports/queries";
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
  failed_import_automation: {
    movies: {
      last_finished_at: null,
      last_outcome: null,
      saved_schedule: "Every 1 hour",
      next_run_note: "Next run follows this saved interval when automation is active.",
    },
    tv_shows: {
      last_finished_at: null,
      last_outcome: null,
      saved_schedule: "Off",
      next_run_note: "Schedule off.",
    },
    source_note: "From persisted task history and saved settings only.",
  },
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
  refiner_worker_count: 0,
  in_process_workers_disabled: true,
  in_process_workers_enabled: false,
  worker_mode_summary: "test",
  refiner_radarr_cleanup_drive_schedule_enabled: false,
  refiner_radarr_cleanup_drive_schedule_interval_seconds: 3600,
  refiner_sonarr_cleanup_drive_schedule_enabled: false,
  refiner_sonarr_cleanup_drive_schedule_interval_seconds: 3600,
  visibility_note: "note",
};

function renderFetcherPage(overview: FetcherOperationalOverview = minimalOverview) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(qk.me, minimalMe);
  qc.setQueryData(fetcherOverviewKey, overview);
  qc.setQueryData(failedImportSettingsQueryKey, minimalFiSettings);
  qc.setQueryData(failedImportInspectionQueryKey("terminal"), { jobs: [], default_terminal_only: true });
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
    expect(t).toMatch(/failed import/i);
    expect(t).toMatch(/service|answered|checks/i);
    expect(t).not.toMatch(/Refiner/i);
  });

  it("second block is compressed service checks, not architecture titles", () => {
    renderFetcherPage();
    expect(screen.getByRole("heading", { name: "Service checks" })).toBeInTheDocument();
    expect(screen.queryByText(/External Fetcher application/i)).toBeNull();
    expect(screen.queryByText(/MEDIAMOP_FETCHER_BASE_URL/i)).toBeNull();
  });

  it("shows a read-only automation summary with separate Movies and TV shows lanes", () => {
    renderFetcherPage();
    expect(screen.getByRole("heading", { name: "Automation summary" })).toBeInTheDocument();
    expect(screen.getByLabelText("Movies")).toBeInTheDocument();
    expect(screen.getByLabelText("TV shows")).toBeInTheDocument();
    expect(screen.getAllByText("Last finished").length).toBe(2);
    expect(screen.getAllByText("Saved schedule").length).toBe(2);
  });

  it("uses honest schedule wording for enabled and off lanes", () => {
    renderFetcherPage();
    expect(screen.getByText("Every 1 hour")).toBeInTheDocument();
    expect(screen.getByText("Next run follows this saved interval when automation is active.")).toBeInTheDocument();
    expect(screen.getByText("Off")).toBeInTheDocument();
    expect(screen.getByText("Schedule off.")).toBeInTheDocument();
  });

  it("does not claim live worker or scheduler health in the automation summary", () => {
    renderFetcherPage();
    const strip = screen.getByTestId("fetcher-automation-summary");
    const text = strip.textContent ?? "";
    expect(text).not.toMatch(/worker health|scheduler health|live worker|live scheduler/i);
  });
});
