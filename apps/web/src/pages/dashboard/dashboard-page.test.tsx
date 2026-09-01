import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { DashboardPage } from "./dashboard-page";

const useDashboardStatusQuery = vi.fn();
const useActivityRecentQuery = vi.fn();
const useRefinerOverviewStatsQuery = vi.fn();
const useRefinerPathSettingsQuery = vi.fn();
const useRefinerJobsInspectionQuery = vi.fn();
const usePrunerOverviewStatsQuery = vi.fn();
const usePrunerInstancesQuery = vi.fn();
const usePrunerJobsInspectionQuery = vi.fn();
const useSuitePauseQuery = vi.fn();

vi.mock("../../lib/activity/queries", () => ({
  activityRecentKey: ["activity", "recent"],
  useActivityRecentQuery: (...args: unknown[]) =>
    useActivityRecentQuery(...args),
}));

vi.mock("../../lib/dashboard/queries", () => ({
  dashboardStatusKey: ["dashboard", "status"],
  useDashboardStatusQuery: (...args: unknown[]) =>
    useDashboardStatusQuery(...args),
}));

vi.mock("../../lib/activity/use-activity-stream-invalidation", () => ({
  useActivityStreamInvalidation: vi.fn(),
  useActivityStreamInvalidations: vi.fn(),
}));

vi.mock("../../lib/refiner/queries", () => ({
  useRefinerOverviewStatsQuery: (...args: unknown[]) =>
    useRefinerOverviewStatsQuery(...args),
  useRefinerPathSettingsQuery: (...args: unknown[]) =>
    useRefinerPathSettingsQuery(...args),
}));

vi.mock("../../lib/refiner/jobs-inspection/queries", () => ({
  useRefinerJobsInspectionQuery: (...args: unknown[]) =>
    useRefinerJobsInspectionQuery(...args),
}));

vi.mock("../../lib/pruner/queries", () => ({
  usePrunerOverviewStatsQuery: (...args: unknown[]) =>
    usePrunerOverviewStatsQuery(...args),
  usePrunerInstancesQuery: (...args: unknown[]) =>
    usePrunerInstancesQuery(...args),
  usePrunerJobsInspectionQuery: (...args: unknown[]) =>
    usePrunerJobsInspectionQuery(...args),
}));

vi.mock("../../lib/suite/pause-queries", () => ({
  useSuitePauseQuery: (...args: unknown[]) => useSuitePauseQuery(...args),
}));

vi.mock("../../lib/ui/mm-format-date", () => ({
  useAppDateFormatter: () => (iso: string) => iso,
}));

beforeAll(() => {
  class EventSourceStub {
    addEventListener = vi.fn();
    removeEventListener = vi.fn();
    close = vi.fn();
  }
  vi.stubGlobal("EventSource", EventSourceStub);
});

describe("DashboardPage", () => {
  beforeEach(() => {
    useDashboardStatusQuery.mockReturnValue({
      isPending: false,
      isError: false,
      data: {
        scope_note: "Read-only overview.",
        system: { api_version: "1.0.0", environment: "test", healthy: true },
        activity_summary: { events_last_24h: 0, latest: null },
      },
    });
    useActivityRecentQuery.mockReturnValue({
      data: {
        items: [],
        total: 0,
        system_events: 0,
      },
    });
    useRefinerOverviewStatsQuery.mockReturnValue({
      data: {
        files_processed: 0,
        files_failed: 0,
        success_rate_percent: 0,
        output_written_count: 0,
        already_optimized_count: 0,
        net_space_saved_bytes: 0,
        net_space_saved_percent: 0,
      },
    });
    useRefinerPathSettingsQuery.mockReturnValue({
      data: {
        refiner_watched_folder: null,
        refiner_watched_folder_exists: false,
        refiner_tv_watched_folder: null,
        refiner_tv_watched_folder_exists: false,
      },
    });
    useRefinerJobsInspectionQuery.mockReturnValue({ data: { jobs: [] } });
    usePrunerOverviewStatsQuery.mockReturnValue({
      data: {
        items_removed: 0,
        items_skipped: 0,
        preview_runs: 0,
        apply_runs: 0,
        failed_applies: 0,
      },
    });
    usePrunerInstancesQuery.mockReturnValue({ data: [] });
    usePrunerJobsInspectionQuery.mockReturnValue({ data: { jobs: [] } });
    useSuitePauseQuery.mockReturnValue({ data: { paused: false } });
  });

  it("explains that paused queue counts include background maintenance", () => {
    useDashboardStatusQuery.mockReturnValue({
      isPending: false,
      isError: false,
      data: {
        scope_note: "Read-only overview.",
        system: { api_version: "1.0.0", environment: "test", healthy: true },
        modules: [
          {
            module: "refiner",
            status: "healthy",
            summary: "Ready.",
            queued_job_count: 2,
            active_job_count: 0,
            failed_job_count: 0,
            action_path: "/refiner?tab=jobs",
          },
        ],
        activity_summary: { events_last_24h: 0, latest: null },
      },
    });
    useSuitePauseQuery.mockReturnValue({ data: { paused: true } });

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    );

    expect(screen.getByText("Jobs held by pause")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Includes maintenance and media work; Resume releases them",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/2 background jobs are safely held by the pause/),
    ).toBeInTheDocument();
  });

  it("renders restored dashboard sections", () => {
    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("dashboard-page")).toBeInTheDocument();
    expect(screen.getByTestId("dashboard-module-cards")).toBeInTheDocument();
    expect(screen.getByTestId("dashboard-needs-attention")).toBeInTheDocument();
    expect(screen.getByTestId("dashboard-active-work")).toBeInTheDocument();
    expect(screen.getByTestId("dashboard-global-jobs")).toBeInTheDocument();
    expect(
      screen.queryByTestId("dashboard-runtime-health"),
    ).not.toBeInTheDocument();
    expect(screen.getAllByText("Refiner").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Pruner").length).toBeGreaterThan(0);
    expect(
      screen.getByText("Needs setup: Refiner, Pruner."),
    ).toBeInTheDocument();
    expect(screen.getByText("Net space saved")).toBeInTheDocument();
    expect(screen.getByText("Removal rate")).toBeInTheDocument();
  });

  it("gives the module cards a column each, so they fill the row", () => {
    // The grid said three columns while only Refiner and Pruner were left, so the cards
    // sat in two thirds of the row with an empty column beside them. Nothing tied the
    // column count to the number of modules, so removing Subber could not have caught it.
    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    );

    const grid = screen.getByTestId("dashboard-module-cards");
    const columns = /xl:grid-cols-(\d+)/.exec(grid.className)?.[1];

    expect(Number(columns)).toBe(grid.children.length);
  });

  it("keeps Refiner scan maintenance noise out of the dashboard", () => {
    useRefinerOverviewStatsQuery.mockReturnValue({
      data: {
        files_processed: 12,
        files_failed: 0,
        success_rate_percent: 100,
        output_written_count: 2,
        already_optimized_count: 0,
        net_space_saved_bytes: 1024,
        net_space_saved_percent: 1.5,
      },
    });
    useRefinerPathSettingsQuery.mockReturnValue({
      data: {
        refiner_watched_folder: "E:\\Completed-Movies",
        refiner_watched_folder_exists: true,
        refiner_tv_watched_folder: null,
        refiner_tv_watched_folder_exists: false,
      },
    });
    useRefinerJobsInspectionQuery.mockReturnValue({
      data: {
        jobs: [
          {
            id: 22,
            dedupe_key: "scan",
            job_kind: "refiner.watched_folder.remux_scan_dispatch.v1",
            status: "completed",
            attempt_count: 1,
            max_attempts: 3,
            lease_owner: null,
            lease_expires_at: null,
            last_error: null,
            payload_json: null,
            created_at: "2026-04-25T10:00:00Z",
            updated_at: "2026-04-25T10:00:00Z",
          },
          {
            id: 23,
            dedupe_key: "file",
            job_kind: "refiner.file.remux_pass.v1",
            status: "completed",
            attempt_count: 1,
            max_attempts: 3,
            lease_owner: null,
            lease_expires_at: null,
            last_error: null,
            payload_json: null,
            created_at: "2026-04-25T10:01:00Z",
            updated_at: "2026-04-25T10:01:00Z",
          },
        ],
      },
    });

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    );

    expect(screen.getByText("Files handled")).toBeInTheDocument();
    expect(
      screen.getByText("2 changed - 0 needed no changes"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Scan watched folders")).not.toBeInTheDocument();
    expect(screen.getByText("Process file")).toBeInTheDocument();
  });

  it("shows worker health problems as attention items", () => {
    useDashboardStatusQuery.mockReturnValue({
      isPending: false,
      isError: false,
      data: {
        scope_note: "Read-only overview.",
        system: {
          api_version: "1.0.0",
          environment: "test",
          healthy: false,
          worker_health: [
            {
              module: "refiner",
              expected_workers: 1,
              active_workers: 0,
              stale_workers: 1,
              stopped_workers: 0,
              status: "degraded",
              detail:
                "Refiner expected 1 worker(s), but 1 are stale, stopped, or missing.",
            },
          ],
        },
        activity_summary: { events_last_24h: 0, latest: null },
      },
    });

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    );

    expect(screen.getAllByText("Review needed").length).toBeGreaterThan(0);
    expect(screen.getByText("Refiner workers")).toBeInTheDocument();
    expect(screen.getByText(/Refiner expected 1 worker/)).toBeInTheDocument();
  });

  it("makes attention states navigable and exposes the history clear path", () => {
    useDashboardStatusQuery.mockReturnValue({
      isPending: false,
      isError: false,
      data: {
        scope_note: "Read-only overview.",
        system: { api_version: "1.0.0", environment: "test", healthy: true },
        activity_summary: { events_last_24h: 0, latest: null },
        incident_count: 1,
      },
    });

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    );

    expect(screen.getByTestId("dashboard-refiner-status-link")).toHaveAttribute(
      "href",
      "/refiner",
    );
    expect(
      screen.getByRole("link", { name: "Clear finished history" }),
    ).toHaveAttribute("href", "/settings?tab=general#history-reset");
  });

  it("keeps long last-activity file names compact without losing the full title", () => {
    const longTitle =
      "Fantastic.Beasts.The.Secrets.of.Dumbledore.2022.UHD.BluRay.2160p.TrueHD.Atmos.FraMeSToR.mkv was processed successfully";
    useActivityRecentQuery.mockReturnValue({
      data: {
        items: [
          {
            id: 1,
            created_at: "2026-05-07T15:45:00Z",
            event_type: "refiner.file.remux_pass_completed",
            module: "refiner",
            title: longTitle,
            detail: null,
          },
        ],
        total: 1,
        system_events: 0,
      },
    });

    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    );

    const signalValue = screen.getAllByTitle(longTitle)[0];
    expect(signalValue).toHaveTextContent(longTitle);
    expect(screen.getAllByText("2026-05-07T15:45:00Z").length).toBeGreaterThan(
      0,
    );
  });
});
