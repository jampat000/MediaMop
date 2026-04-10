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

describe("FetcherPage (failed-import ownership)", () => {
  it("renders download-queue failed-import workspace under Fetcher", () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(qk.me, minimalMe);
    qc.setQueryData(fetcherOverviewKey, minimalOverview);
    qc.setQueryData(failedImportSettingsQueryKey, minimalFiSettings);
    qc.setQueryData(failedImportInspectionQueryKey("terminal"), { jobs: [], default_terminal_only: true });

    render(wrap(<FetcherPage />, qc));

    expect(screen.getByTestId("fetcher-failed-imports-workspace")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /download-queue failed imports/i })).toBeInTheDocument();
  });

  it("frames Radarr/Sonarr queue work in the Fetcher page header", () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(qk.me, minimalMe);
    qc.setQueryData(fetcherOverviewKey, minimalOverview);
    qc.setQueryData(failedImportSettingsQueryKey, minimalFiSettings);
    qc.setQueryData(failedImportInspectionQueryKey("terminal"), { jobs: [], default_terminal_only: true });

    render(wrap(<FetcherPage />, qc));

    const h1 = screen.getByRole("heading", { level: 1, name: "Fetcher" });
    expect(h1).toBeInTheDocument();
    const intro = h1.closest("header");
    expect(intro?.textContent).toMatch(/Radarr/i);
    expect(intro?.textContent).toMatch(/Sonarr/i);
    expect(intro?.textContent).toMatch(/download-queue/i);
  });
});
