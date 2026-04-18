import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { UserPublic } from "../../lib/api/types";
import * as authQueries from "../../lib/auth/queries";
import * as subberQueries from "../../lib/subber/subber-queries";
import { SubberPage } from "./subber-page";

const adminUser: UserPublic = { id: 1, username: "admin", role: "admin" };

function wrap(ui: ReactNode, client: QueryClient) {
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("SubberPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    vi.spyOn(authQueries, "useMeQuery").mockReturnValue({
      data: adminUser,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof authQueries.useMeQuery>);
    vi.spyOn(subberQueries, "useSubberOverviewQuery").mockReturnValue({
      data: {
        total_tracked: 0,
        found: 0,
        missing: 0,
        searching: 0,
        skipped: 0,
        searches_today: 0,
        per_language: [],
      },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberOverviewQuery>);
    vi.spyOn(subberQueries, "useSubberSettingsQuery").mockReturnValue({
      data: {
        enabled: false,
        opensubtitles_username: "",
        opensubtitles_password_set: false,
        opensubtitles_api_key_set: false,
        sonarr_base_url: "",
        sonarr_api_key_set: false,
        radarr_base_url: "",
        radarr_api_key_set: false,
        language_preferences: ["en"],
        subtitle_folder: "",
        tv_schedule_enabled: false,
        tv_schedule_interval_seconds: 3600,
        tv_schedule_hours_limited: false,
        tv_schedule_days: "",
        tv_schedule_start: "00:00",
        tv_schedule_end: "23:59",
        movies_schedule_enabled: false,
        movies_schedule_interval_seconds: 3600,
        movies_schedule_hours_limited: false,
        movies_schedule_days: "",
        movies_schedule_start: "00:00",
        movies_schedule_end: "23:59",
        tv_last_scheduled_scan_enqueued_at: null,
        movies_last_scheduled_scan_enqueued_at: null,
        fetcher_sonarr_base_url_hint: "",
        fetcher_radarr_base_url_hint: "",
      },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberSettingsQuery>);
    vi.spyOn(subberQueries, "useSubberLibraryTvQuery").mockReturnValue({
      data: { shows: [] },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberLibraryTvQuery>);
    vi.spyOn(subberQueries, "useSubberLibraryMoviesQuery").mockReturnValue({
      data: { movies: [] },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberLibraryMoviesQuery>);
    vi.spyOn(subberQueries, "useSubberJobsQuery").mockReturnValue({
      data: { jobs: [], default_recent_slice: true },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberJobsQuery>);
    vi.spyOn(subberQueries, "usePutSubberSettingsMutation").mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof subberQueries.usePutSubberSettingsMutation>);
    vi.spyOn(subberQueries, "useSubberSearchNowMutation").mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberSearchNowMutation>);
    vi.spyOn(subberQueries, "useSubberSearchAllMissingTvMutation").mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberSearchAllMissingTvMutation>);
    vi.spyOn(subberQueries, "useSubberSearchAllMissingMoviesMutation").mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberSearchAllMissingMoviesMutation>);
    vi.spyOn(subberQueries, "useSubberTestOpensubtitlesMutation").mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberTestOpensubtitlesMutation>);
    vi.spyOn(subberQueries, "useSubberTestSonarrMutation").mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberTestSonarrMutation>);
    vi.spyOn(subberQueries, "useSubberTestRadarrMutation").mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberTestRadarrMutation>);
  });

  it("renders tabs with Overview selected by default", async () => {
    const client = new QueryClient();
    render(wrap(<SubberPage />, client));
    await waitFor(() => expect(screen.getByTestId("subber-top-level-tabs")).toBeInTheDocument());
    const tabs = screen.getByTestId("subber-top-level-tabs");
    expect(tabs.textContent).toMatch(/Overview/);
    expect(tabs.textContent).toMatch(/TV/);
    expect(screen.getByTestId("subber-overview-tab")).toBeInTheDocument();
  });

  it("switches to TV tab", async () => {
    const client = new QueryClient();
    render(wrap(<SubberPage />, client));
    await waitFor(() => expect(screen.getByTestId("subber-top-level-tabs")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("tab", { name: "TV" }));
    await waitFor(() => expect(screen.getByTestId("subber-tv-tab")).toBeInTheDocument());
  });
});
