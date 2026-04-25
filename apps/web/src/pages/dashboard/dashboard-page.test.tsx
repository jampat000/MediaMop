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
const useSubberOverviewQuery = vi.fn();
const useSubberSettingsQuery = vi.fn();
const useSubberProvidersQuery = vi.fn();
const useSubberJobsQuery = vi.fn();

vi.mock("../../lib/activity/queries", () => ({
  activityRecentKey: ["activity", "recent"],
  useActivityRecentQuery: (...args: unknown[]) => useActivityRecentQuery(...args),
}));

vi.mock("../../lib/dashboard/queries", () => ({
  dashboardStatusKey: ["dashboard", "status"],
  useDashboardStatusQuery: (...args: unknown[]) => useDashboardStatusQuery(...args),
}));

vi.mock("../../lib/activity/use-activity-stream-invalidation", () => ({
  useActivityStreamInvalidation: vi.fn(),
  useActivityStreamInvalidations: vi.fn(),
}));

vi.mock("../../lib/refiner/queries", () => ({
  useRefinerOverviewStatsQuery: (...args: unknown[]) => useRefinerOverviewStatsQuery(...args),
  useRefinerPathSettingsQuery: (...args: unknown[]) => useRefinerPathSettingsQuery(...args),
}));

vi.mock("../../lib/refiner/jobs-inspection/queries", () => ({
  useRefinerJobsInspectionQuery: (...args: unknown[]) => useRefinerJobsInspectionQuery(...args),
}));

vi.mock("../../lib/pruner/queries", () => ({
  usePrunerOverviewStatsQuery: (...args: unknown[]) => usePrunerOverviewStatsQuery(...args),
  usePrunerInstancesQuery: (...args: unknown[]) => usePrunerInstancesQuery(...args),
  usePrunerJobsInspectionQuery: (...args: unknown[]) => usePrunerJobsInspectionQuery(...args),
}));

vi.mock("../../lib/subber/subber-queries", () => ({
  useSubberOverviewQuery: (...args: unknown[]) => useSubberOverviewQuery(...args),
  useSubberSettingsQuery: (...args: unknown[]) => useSubberSettingsQuery(...args),
  useSubberProvidersQuery: (...args: unknown[]) => useSubberProvidersQuery(...args),
  useSubberJobsQuery: (...args: unknown[]) => useSubberJobsQuery(...args),
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
    useSubberOverviewQuery.mockReturnValue({
      data: {
        subtitles_downloaded: 0,
        still_missing: 0,
        tv_tracked: 0,
        movies_tracked: 0,
        tv_missing: 0,
        movies_missing: 0,
        found_last_30_days: 0,
        not_found_last_30_days: 0,
        upgrades_last_30_days: 0,
      },
    });
    useSubberSettingsQuery.mockReturnValue({ data: { sonarr_base_url: "", sonarr_api_key_set: false, radarr_base_url: "", radarr_api_key_set: false } });
    useSubberProvidersQuery.mockReturnValue({ data: [] });
    useSubberJobsQuery.mockReturnValue({ data: { jobs: [] } });
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
    expect(screen.queryByTestId("dashboard-runtime-health")).not.toBeInTheDocument();
    expect(screen.getByText("Refiner")).toBeInTheDocument();
    expect(screen.getByText("Pruner")).toBeInTheDocument();
    expect(screen.getByText("Subber")).toBeInTheDocument();
    expect(screen.getByText("Net space saved")).toBeInTheDocument();
    expect(screen.getByText("Removal rate")).toBeInTheDocument();
    expect(screen.getByText("Coverage")).toBeInTheDocument();
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
    expect(screen.getByText("2 changed - 0 needed no changes")).toBeInTheDocument();
    expect(screen.queryByText("Scan watched folders")).not.toBeInTheDocument();
    expect(screen.getByText("Process file")).toBeInTheDocument();
  });
});
