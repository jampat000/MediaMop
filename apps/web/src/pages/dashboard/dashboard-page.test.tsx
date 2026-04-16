import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { DashboardStatus } from "../../lib/api/types";
import { activityRecentKey } from "../../lib/activity/queries";
import { dashboardStatusKey } from "../../lib/dashboard/queries";
import { fetcherArrOperatorSettingsQueryKey } from "../../lib/fetcher/arr-operator-settings/queries";
import { failedImportQueueAttentionSnapshotQueryKey } from "../../lib/fetcher/failed-imports/queries";
import { fetcherJobsInspectionQueryKey } from "../../lib/fetcher/jobs-inspection/queries";
import { DashboardPage } from "./dashboard-page";

class EventSourceMock {
  addEventListener() {}
  removeEventListener() {}
  close() {}
}

(globalThis as { EventSource?: unknown }).EventSource = EventSourceMock;

const dashboardData: DashboardStatus = {
  scope_note: "Read-only overview.",
  system: { api_version: "0.0.1", environment: "dev", healthy: true },
  fetcher: {
    configured: true,
    target_display: "http://localhost:5656",
    reachable: true,
    http_status: 200,
    latency_ms: 12,
    fetcher_app: "Fetcher",
    fetcher_version: "1.0.0",
    detail: null,
  },
  activity_summary: {
    events_last_24h: 3,
    latest: null,
    last_fetcher_probe: null,
  },
};

function wrap(ui: ReactNode, qc: QueryClient) {
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

function renderDashboard(args?: { sonarrConfigured?: boolean; radarrConfigured?: boolean }) {
  const sonarrConfigured = args?.sonarrConfigured ?? true;
  const radarrConfigured = args?.radarrConfigured ?? true;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(dashboardStatusKey, dashboardData);
  qc.setQueryData(activityRecentKey, {
    items: [{ id: 1, created_at: "2026-04-14T00:00:00Z", event_type: "fetcher.x", module: "fetcher", title: "Queued", detail: null }],
  });
  qc.setQueryData(fetcherArrOperatorSettingsQueryKey, {
    sonarr_server_configured: sonarrConfigured,
    radarr_server_configured: radarrConfigured,
  });
  qc.setQueryData(failedImportQueueAttentionSnapshotQueryKey, {
    tv_shows: { needs_attention_count: 2, last_checked_at: null },
    movies: { needs_attention_count: 0, last_checked_at: null },
  });
  qc.setQueryData(fetcherJobsInspectionQueryKey("pending"), { jobs: [{ id: 1 }], default_terminal_only: false });
  qc.setQueryData(fetcherJobsInspectionQueryKey("leased"), { jobs: [{ id: 2 }], default_terminal_only: false });
  return render(wrap(<DashboardPage />, qc));
}

describe("DashboardPage", () => {
  it("renders the locked dashboard sections in order", () => {
    renderDashboard();
    expect(screen.getByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByTestId("dashboard-status-strip")).toBeInTheDocument();
    expect(screen.getByTestId("dashboard-module-cards")).toBeInTheDocument();
    expect(screen.getByTestId("dashboard-needs-attention")).toBeInTheDocument();
    expect(screen.getByTestId("dashboard-active-work")).toBeInTheDocument();
  });

  it("shows uniform module action buttons and TV/Movies rows", () => {
    renderDashboard();
    expect(screen.getByRole("link", { name: "Open Fetcher" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Refiner" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Pruner" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Subber" })).toBeInTheDocument();
    expect(screen.getAllByText(/TV:/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Movies:/i).length).toBeGreaterThan(0);
  });

  it("keeps status strip and needs-attention consistent when fetcher setup is incomplete", () => {
    renderDashboard({ sonarrConfigured: false, radarrConfigured: true });
    expect(screen.getByText("Setup needed")).toBeInTheDocument();
    expect(screen.getByTestId("dashboard-status-strip")).not.toHaveTextContent("Modules needing attentionNone detected");
    expect(screen.getByTestId("dashboard-needs-attention")).toHaveTextContent("Fetcher: Set up Sonarr");
  });
});
