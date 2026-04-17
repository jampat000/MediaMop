import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as prunerApi from "../../lib/pruner/api";
import { PrunerInstancesListPage } from "./pruner-instances-list-page";

function wrap(ui: ReactNode, client: QueryClient) {
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("PrunerInstancesListPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders top-level Pruner tabs Overview/Emby/Jellyfin/Plex/Schedules/Jobs", async () => {
    const client = new QueryClient();
    vi.spyOn(prunerApi, "fetchPrunerInstances").mockResolvedValue([]);
    vi.spyOn(prunerApi, "fetchPrunerJobsInspection").mockResolvedValue({ jobs: [], default_recent_slice: true });

    render(wrap(<PrunerInstancesListPage />, client));

    await waitFor(() => expect(screen.getByTestId("pruner-top-level-tabs")).toBeInTheDocument());
    const tabs = screen.getByTestId("pruner-top-level-tabs");
    expect(tabs.textContent).toMatch(/Overview/);
    expect(tabs.textContent).toMatch(/Emby/);
    expect(tabs.textContent).toMatch(/Jellyfin/);
    expect(tabs.textContent).toMatch(/Plex/);
    expect(tabs.textContent).toMatch(/Schedules/);
    expect(tabs.textContent).toMatch(/Jobs/);
  });

  it("provider tabs render connection form and flat configuration without registered instance", async () => {
    const client = new QueryClient();
    vi.spyOn(prunerApi, "fetchPrunerInstances").mockResolvedValue([]);
    vi.spyOn(prunerApi, "fetchPrunerJobsInspection").mockResolvedValue({ jobs: [], default_recent_slice: true });
    vi.spyOn(prunerApi, "postPrunerInstance").mockResolvedValue({
      id: 11,
      provider: "emby",
      display_name: "Emby Home",
      base_url: "http://emby.local",
      enabled: true,
      last_connection_test_at: null,
      last_connection_test_ok: null,
      last_connection_test_detail: null,
      scopes: [],
    });

    render(wrap(<PrunerInstancesListPage />, client));

    await waitFor(() => expect(screen.getByTestId("pruner-top-level-tabs")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Emby" }));
    await waitFor(() => expect(screen.getByTestId("pruner-provider-tab-emby")).toBeInTheDocument());
    expect(screen.getByTestId("pruner-provider-connection-emby")).toBeInTheDocument();
    expect(screen.getByLabelText(/Server URL/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/API key/i)).toBeInTheDocument();
    expect(screen.getByTestId("pruner-provider-configuration-emby")).toBeInTheDocument();
    expect(screen.getByText(/TV \(episodes\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Movies \(one row per movie item\)/i)).toBeInTheDocument();
    expect(screen.getAllByTestId("pruner-run-limits-panel").length).toBe(2);
    expect(screen.getByText(/Enable watched TV rule for this TV tab/i)).toBeInTheDocument();
    expect(screen.getByText(/Enable never-played TV older-than rule for this tab/i)).toBeInTheDocument();
    expect(screen.getByText(/Enable watched movies rule for this Movies tab/i)).toBeInTheDocument();
    expect(screen.getByText(/Enable unwatched stale movies rule for this Movies tab/i)).toBeInTheDocument();
    const disabledFieldsets = screen.getByTestId("pruner-provider-configuration-emby").querySelectorAll("fieldset[disabled]");
    expect(disabledFieldsets.length).toBe(2);
    expect(screen.queryByTestId("pruner-provider-sections-emby")).not.toBeInTheDocument();
  });

  it("shows provider-first zero-instance framing with Emby, Jellyfin, and Plex named", async () => {
    const client = new QueryClient();
    vi.spyOn(prunerApi, "fetchPrunerInstances").mockResolvedValue([]);
    vi.spyOn(prunerApi, "fetchPrunerJobsInspection").mockResolvedValue({ jobs: [], default_recent_slice: true });

    render(wrap(<PrunerInstancesListPage />, client));

    await waitFor(() => expect(screen.getByTestId("pruner-empty-state")).toBeInTheDocument());
    const page = screen.getByTestId("pruner-scope-page");
    expect(page.textContent).toContain("Emby");
    expect(page.textContent).toContain("Jellyfin");
    expect(page.textContent).toContain("Plex");
    expect(screen.getByTestId("pruner-empty-state").textContent ?? "").toMatch(/nothing is shared across providers/i);
  });

  it("Plex provider uses token wording and keeps unsupported Plex rule truth visible", async () => {
    const client = new QueryClient();
    vi.spyOn(prunerApi, "fetchPrunerInstances").mockResolvedValue([
      {
        id: 3,
        provider: "plex",
        display_name: "Plex Home",
        base_url: "http://plex.test",
        enabled: true,
        last_connection_test_at: null,
        last_connection_test_ok: null,
        last_connection_test_detail: null,
        scopes: [],
      },
    ]);
    vi.spyOn(prunerApi, "fetchPrunerJobsInspection").mockResolvedValue({ jobs: [], default_recent_slice: true });

    render(wrap(<PrunerInstancesListPage />, client));

    fireEvent.click(screen.getByRole("button", { name: "Plex" }));
    await waitFor(() => expect(screen.getByTestId("pruner-provider-tab-plex")).toBeInTheDocument());
    expect(screen.getByLabelText(/Token/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/API key/i)).not.toBeInTheDocument();
    expect(screen.getByTestId("pruner-provider-plex-unsupported-note").textContent ?? "").toMatch(/unsupported/i);
  });

  it("provider page keeps TV and Movies as sections (not tabs) when instance exists", async () => {
    const client = new QueryClient();
    vi.spyOn(prunerApi, "fetchPrunerInstances").mockResolvedValue([
      {
        id: 2,
        provider: "emby",
        display_name: "Home",
        base_url: "http://emby.test",
        enabled: true,
        last_connection_test_at: null,
        last_connection_test_ok: null,
        last_connection_test_detail: null,
        scopes: [
          {
            media_scope: "tv",
            missing_primary_media_reported_enabled: true,
            never_played_stale_reported_enabled: false,
            never_played_min_age_days: 90,
            watched_tv_reported_enabled: true,
            watched_movies_reported_enabled: false,
            watched_movie_low_rating_reported_enabled: false,
            watched_movie_low_rating_max_jellyfin_emby_community_rating: 4,
            watched_movie_low_rating_max_plex_audience_rating: 4,
            unwatched_movie_stale_reported_enabled: false,
            unwatched_movie_stale_min_age_days: 90,
            preview_max_items: 500,
            preview_include_genres: [],
            preview_include_people: [],
            preview_year_min: null,
            preview_year_max: null,
            preview_include_studios: [],
            preview_include_collections: [],
            scheduled_preview_enabled: false,
            scheduled_preview_interval_seconds: 3600,
            last_scheduled_preview_enqueued_at: null,
            last_preview_run_uuid: null,
            last_preview_at: null,
            last_preview_candidate_count: null,
            last_preview_outcome: null,
            last_preview_error: null,
          },
          {
            media_scope: "movies",
            missing_primary_media_reported_enabled: true,
            never_played_stale_reported_enabled: true,
            never_played_min_age_days: 90,
            watched_tv_reported_enabled: false,
            watched_movies_reported_enabled: true,
            watched_movie_low_rating_reported_enabled: true,
            watched_movie_low_rating_max_jellyfin_emby_community_rating: 4,
            watched_movie_low_rating_max_plex_audience_rating: 4,
            unwatched_movie_stale_reported_enabled: true,
            unwatched_movie_stale_min_age_days: 90,
            preview_max_items: 500,
            preview_include_genres: [],
            preview_include_people: [],
            preview_year_min: null,
            preview_year_max: null,
            preview_include_studios: [],
            preview_include_collections: [],
            scheduled_preview_enabled: false,
            scheduled_preview_interval_seconds: 3600,
            last_scheduled_preview_enqueued_at: null,
            last_preview_run_uuid: null,
            last_preview_at: null,
            last_preview_candidate_count: null,
            last_preview_outcome: null,
            last_preview_error: null,
          },
        ],
      },
    ]);
    vi.spyOn(prunerApi, "fetchPrunerJobsInspection").mockResolvedValue({ jobs: [], default_recent_slice: true });
    vi.spyOn(prunerApi, "fetchPrunerPreviewRuns").mockResolvedValue([]);

    render(wrap(<PrunerInstancesListPage />, client));

    fireEvent.click(screen.getByRole("button", { name: "Emby" }));
    await waitFor(() => expect(screen.getByTestId("pruner-provider-tab-emby")).toBeInTheDocument());
    expect(screen.getByText(/TV \(episodes\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Movies \(one row per movie item\)/i)).toBeInTheDocument();
    expect(screen.getAllByTestId("pruner-run-limits-panel").length).toBe(2);
    const disabledFieldsets = screen.getByTestId("pruner-provider-configuration-emby").querySelectorAll("fieldset[disabled]");
    expect(disabledFieldsets.length).toBe(0);
    expect(screen.queryByTestId("pruner-provider-sections-emby")).not.toBeInTheDocument();
  });
});
