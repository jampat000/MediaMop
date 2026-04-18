import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { UserPublic } from "../../lib/api/types";
import * as authApi from "../../lib/api/auth-api";
import { qk } from "../../lib/auth/queries";
import * as prunerApi from "../../lib/pruner/api";
import { PrunerInstancesListPage } from "./pruner-instances-list-page";

const adminUser: UserPublic = { id: 1, username: "admin", role: "admin" };

function wrap(ui: ReactNode, client: QueryClient) {
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("PrunerInstancesListPage", () => {
  beforeEach(() => {
    vi.spyOn(prunerApi, "fetchPrunerStudios").mockResolvedValue({ studios: ["Acme Studio", "Beta Pictures"] });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders top-level tabs Overview, Emby, Jellyfin, Plex, Jobs without Connections or Schedules", async () => {
    const client = new QueryClient();
    vi.spyOn(prunerApi, "fetchPrunerInstances").mockResolvedValue([]);
    vi.spyOn(prunerApi, "fetchPrunerJobsInspection").mockResolvedValue({ jobs: [], default_recent_slice: true });

    render(wrap(<PrunerInstancesListPage />, client));

    await waitFor(() => expect(screen.getByTestId("pruner-top-level-tabs")).toBeInTheDocument());
    const tabs = screen.getByTestId("pruner-top-level-tabs");
    expect(tabs.textContent).toMatch(/Overview/);
    expect(tabs.textContent).not.toMatch(/Connections/);
    expect(tabs.textContent).toMatch(/Emby/);
    expect(tabs.textContent).toMatch(/Jellyfin/);
    expect(tabs.textContent).toMatch(/Plex/);
    expect(tabs.textContent).not.toMatch(/Schedules/);
    expect(tabs.textContent).toMatch(/Jobs/);
  });

  it("each provider tab exposes Connection, Cleanup, and Schedule sub-tabs with a credential panel on Connection", async () => {
    const client = new QueryClient();
    vi.spyOn(prunerApi, "fetchPrunerInstances").mockResolvedValue([]);
    vi.spyOn(prunerApi, "fetchPrunerJobsInspection").mockResolvedValue({ jobs: [], default_recent_slice: true });

    render(wrap(<PrunerInstancesListPage />, client));

    await waitFor(() => expect(screen.getByTestId("pruner-top-level-tabs")).toBeInTheDocument());

    for (const name of ["Emby", "Jellyfin", "Plex"] as const) {
      fireEvent.click(screen.getByRole("tab", { name }));
      await waitFor(() => expect(screen.getByTestId(`pruner-provider-tab-${name.toLowerCase()}`)).toBeInTheDocument());
      const sub = screen.getByTestId(`pruner-provider-subnav-${name.toLowerCase()}`);
      expect(within(sub).getByRole("button", { name: "Connection" })).toBeInTheDocument();
      expect(within(sub).getByRole("button", { name: "Cleanup" })).toBeInTheDocument();
      expect(within(sub).getByRole("button", { name: "Schedule" })).toBeInTheDocument();
      expect(screen.getByTestId(`pruner-connection-panel-${name.toLowerCase()}`)).toBeInTheDocument();
      expect(screen.getByLabelText(/^Base URL$/i)).toBeInTheDocument();
    }
  });

  it("Plex Connection sub-tab uses Token label, not API key", async () => {
    const client = new QueryClient();
    vi.spyOn(prunerApi, "fetchPrunerInstances").mockResolvedValue([]);
    vi.spyOn(prunerApi, "fetchPrunerJobsInspection").mockResolvedValue({ jobs: [], default_recent_slice: true });

    render(wrap(<PrunerInstancesListPage />, client));

    fireEvent.click(screen.getByRole("tab", { name: "Plex" }));
    await waitFor(() => expect(screen.getByTestId("pruner-connection-panel-plex")).toBeInTheDocument());
    const plexPanel = screen.getByTestId("pruner-connection-panel-plex");
    expect(within(plexPanel).getByLabelText(/^Token$/i)).toBeInTheDocument();
    expect(within(plexPanel).queryByLabelText(/^API key$/i)).not.toBeInTheDocument();
  });

  it("Emby tab shows Cleanup sub-navigation, TV/Movies columns, and no nested top-level tabs inside the workspace", async () => {
    const client = new QueryClient();
    client.setQueryData(qk.me, adminUser);
    const scope = (media_scope: "tv" | "movies") => ({
      media_scope,
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
    });
    vi.spyOn(prunerApi, "fetchPrunerInstances").mockResolvedValue([
      {
        id: 22,
        provider: "emby",
        display_name: "Emby",
        base_url: "http://emby.test",
        enabled: true,
        last_connection_test_at: null,
        last_connection_test_ok: null,
        last_connection_test_detail: null,
        scopes: [scope("tv"), scope("movies")],
      },
    ]);
    vi.spyOn(prunerApi, "fetchPrunerJobsInspection").mockResolvedValue({ jobs: [], default_recent_slice: true });

    render(wrap(<PrunerInstancesListPage />, client));

    await waitFor(() => expect(screen.getByTestId("pruner-top-level-tabs")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("tab", { name: "Emby" }));
    await waitFor(() => expect(screen.getByTestId("pruner-provider-tab-emby")).toBeInTheDocument());
    expect(screen.getByTestId("pruner-provider-subnav-emby")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connection" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cleanup" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Filters" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cleanup" }));
    await waitFor(() => expect(screen.getByTestId("pruner-provider-configuration-emby")).toBeInTheDocument());
    const rulesCard = screen.getByTestId("pruner-provider-configuration-emby");
    expect(within(screen.getByTestId("pruner-provider-tab-emby")).queryByRole("heading", { level: 2, name: /^Emby$/ })).not.toBeInTheDocument();
    expect(within(rulesCard).getAllByText(/^TV$/).length).toBeGreaterThanOrEqual(1);
    expect(within(rulesCard).getAllByText(/^Movies$/).length).toBeGreaterThanOrEqual(1);
    expect(rulesCard).toBeInTheDocument();
    expect(within(rulesCard).queryByRole("tab")).toBeNull();
    expect(screen.queryByRole("button", { name: /Save watched TV rule/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save TV criteria" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save Movies criteria" })).toBeInTheDocument();
    expect(screen.getByTestId("pruner-cleanup-run-tv-btn")).toBeInTheDocument();
    expect(screen.getByTestId("pruner-cleanup-run-movies-btn")).toBeInTheDocument();
  });

  it("Cleanup tab shows TV and Movies people fields and run controls", async () => {
    const client = new QueryClient();
    client.setQueryData(qk.me, adminUser);
    const scope = (media_scope: "tv" | "movies") => ({
      media_scope,
      missing_primary_media_reported_enabled: true,
      never_played_stale_reported_enabled: false,
      never_played_min_age_days: 90,
      watched_tv_reported_enabled: false,
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
    });
    vi.spyOn(prunerApi, "fetchPrunerInstances").mockResolvedValue([
      {
        id: 44,
        provider: "emby",
        display_name: "Emby",
        base_url: "http://emby.test",
        enabled: true,
        last_connection_test_at: null,
        last_connection_test_ok: null,
        last_connection_test_detail: null,
        scopes: [scope("tv"), scope("movies")],
      },
    ]);
    vi.spyOn(prunerApi, "fetchPrunerJobsInspection").mockResolvedValue({ jobs: [], default_recent_slice: true });

    render(wrap(<PrunerInstancesListPage />, client));

    await waitFor(() => expect(screen.getByTestId("pruner-top-level-tabs")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("tab", { name: "Emby" }));
    await waitFor(() => expect(screen.getByTestId("pruner-provider-tab-emby")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Cleanup" }));
    await waitFor(() => expect(screen.getByTestId("pruner-provider-configuration-emby")).toBeInTheDocument());
    const cleanupWrap = screen.getByTestId("pruner-provider-cleanup-wrap");
    expect(within(cleanupWrap).queryByTestId("pruner-provider-inline-connection-status")).not.toBeInTheDocument();
    const card = screen.getByTestId("pruner-provider-configuration-emby");
    expect(within(card).getAllByPlaceholderText(/Alex Carter/i)).toHaveLength(2);
    expect(screen.getByTestId("pruner-cleanup-run-tv-btn")).toBeInTheDocument();
    expect(screen.getByTestId("pruner-cleanup-run-movies-btn")).toBeInTheDocument();
  });

  it("Connection sub-tab shows Connected in status when last Emby test passed", async () => {
    const client = new QueryClient();
    client.setQueryData(qk.me, adminUser);
    const scope = (media_scope: "tv" | "movies") => ({
      media_scope,
      missing_primary_media_reported_enabled: true,
      never_played_stale_reported_enabled: false,
      never_played_min_age_days: 90,
      watched_tv_reported_enabled: false,
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
    });
    vi.spyOn(prunerApi, "fetchPrunerInstances").mockResolvedValue([
      {
        id: 99,
        provider: "emby",
        display_name: "Emby",
        base_url: "http://emby.test",
        enabled: true,
        last_connection_test_at: "2020-01-01T00:00:00Z",
        last_connection_test_ok: true,
        last_connection_test_detail: null,
        scopes: [scope("tv"), scope("movies")],
      },
    ]);
    vi.spyOn(prunerApi, "fetchPrunerJobsInspection").mockResolvedValue({ jobs: [], default_recent_slice: true });

    render(wrap(<PrunerInstancesListPage />, client));

    await waitFor(() => expect(screen.getByTestId("pruner-top-level-tabs")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("tab", { name: "Emby" }));
    fireEvent.click(screen.getByRole("button", { name: "Connection" }));
    await waitFor(() => expect(screen.getByTestId("pruner-connection-panel-emby")).toBeInTheDocument());
    const statusBox = screen.getByTestId("pruner-connection-status-emby");
    expect(within(statusBox).getByText("Connected")).toBeInTheDocument();
  });

  it("pre-connection Emby Cleanup tab is editable without connection banner", async () => {
    const client = new QueryClient();
    client.setQueryData(qk.me, adminUser);
    vi.spyOn(prunerApi, "fetchPrunerInstances").mockResolvedValue([]);
    vi.spyOn(prunerApi, "fetchPrunerJobsInspection").mockResolvedValue({ jobs: [], default_recent_slice: true });

    render(wrap(<PrunerInstancesListPage />, client));

    fireEvent.click(screen.getByRole("tab", { name: "Emby" }));
    await waitFor(() => expect(screen.getByTestId("pruner-provider-tab-emby")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Cleanup" }));
    await waitFor(() => expect(screen.getByTestId("pruner-provider-configuration-emby")).toBeInTheDocument());
    expect(screen.queryByTestId("pruner-provider-inline-connection-status")).not.toBeInTheDocument();
    expect(screen.queryByText(/Save a connection first to enable these settings/i)).not.toBeInTheDocument();
    const disabledFieldsets = screen.getByTestId("pruner-provider-configuration-emby").querySelectorAll("fieldset[disabled]");
    expect(disabledFieldsets.length).toBe(0);
    expect(screen.getByText(/Delete TV episodes you have already watched/i)).toBeInTheDocument();
  });

  it("Plex Cleanup tab shows only supported controls: TV missing-primary + filters + people; Movies without missing-primary toggle", async () => {
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
        scopes: [
          {
            media_scope: "tv",
            missing_primary_media_reported_enabled: true,
            never_played_stale_reported_enabled: false,
            never_played_min_age_days: 90,
            watched_tv_reported_enabled: false,
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
            never_played_stale_reported_enabled: false,
            never_played_min_age_days: 90,
            watched_tv_reported_enabled: false,
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
        ],
      },
    ]);
    vi.spyOn(prunerApi, "fetchPrunerJobsInspection").mockResolvedValue({ jobs: [], default_recent_slice: true });

    render(wrap(<PrunerInstancesListPage />, client));

    fireEvent.click(screen.getByRole("tab", { name: "Plex" }));
    await waitFor(() => expect(screen.getByTestId("pruner-provider-tab-plex")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Cleanup" }));
    await waitFor(() => expect(screen.getByTestId("pruner-provider-configuration-plex")).toBeInTheDocument());
    const plexTvNote = screen.getByTestId("pruner-plex-tv-rules-scope-note");
    expect(plexTvNote).toHaveTextContent(/Plex TV — limited options/i);
    expect(plexTvNote).toHaveTextContent(/missing poster rule is available here/i);
    expect(screen.queryByTestId("pruner-provider-plex-tv-unsupported-rules")).not.toBeInTheDocument();
    expect(screen.queryByTestId("pruner-plex-tv-filters-scope-note")).not.toBeInTheDocument();
    expect(screen.queryByTestId("pruner-plex-other-rules-note")).not.toBeInTheDocument();
    const tvSection = screen.getByTestId("pruner-provider-tv-config-plex");
    expect(within(tvSection).queryByText(/Delete TV episodes you have already watched/i)).not.toBeInTheDocument();
    expect(within(tvSection).getByTestId("pruner-provider-tv-people-plex")).toBeInTheDocument();
    const moviesSection = screen.getByTestId("pruner-provider-movies-config-plex");
    expect(within(moviesSection).getByText(/Plex audience rating/i)).toBeInTheDocument();
    expect(within(moviesSection).queryByText(/Delete movies missing a main poster/i)).not.toBeInTheDocument();
  });

  it("Plex Cleanup tab TV people roles show Cast, Directors, and Writers only", async () => {
    const client = new QueryClient();
    client.setQueryData(qk.me, adminUser);
    const scope = (media_scope: "tv" | "movies") => ({
      media_scope,
      missing_primary_media_reported_enabled: true,
      never_played_stale_reported_enabled: false,
      never_played_min_age_days: 90,
      watched_tv_reported_enabled: false,
      watched_movies_reported_enabled: false,
      watched_movie_low_rating_reported_enabled: false,
      watched_movie_low_rating_max_jellyfin_emby_community_rating: 4,
      watched_movie_low_rating_max_plex_audience_rating: 4,
      unwatched_movie_stale_reported_enabled: false,
      unwatched_movie_stale_min_age_days: 90,
      preview_max_items: 500,
      preview_include_genres: [],
      preview_include_people: [],
      preview_include_people_roles: ["cast"],
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
    });
    vi.spyOn(prunerApi, "fetchPrunerInstances").mockResolvedValue([
      {
        id: 77,
        provider: "plex",
        display_name: "Plex",
        base_url: "http://plex.test",
        enabled: true,
        last_connection_test_at: null,
        last_connection_test_ok: null,
        last_connection_test_detail: null,
        scopes: [scope("tv"), scope("movies")],
      },
    ]);
    vi.spyOn(prunerApi, "fetchPrunerJobsInspection").mockResolvedValue({ jobs: [], default_recent_slice: true });

    render(wrap(<PrunerInstancesListPage />, client));

    await waitFor(() => expect(screen.getByTestId("pruner-top-level-tabs")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("tab", { name: "Plex" }));
    await waitFor(() => expect(screen.getByTestId("pruner-provider-tab-plex")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Cleanup" }));
    await waitFor(() => expect(screen.getByTestId("pruner-provider-configuration-plex")).toBeInTheDocument());
    const card = screen.getByTestId("pruner-provider-configuration-plex");
    expect(within(card).getAllByText("Cast (actors)")).toHaveLength(2);
    const tvRoles = within(card).getByTestId("pruner-provider-tv-people-roles-plex");
    expect(within(tvRoles).getByText("Directors")).toBeInTheDocument();
    expect(within(tvRoles).getByText("Writers")).toBeInTheDocument();
    expect(within(card).queryByText(/Producers/i)).not.toBeInTheDocument();
    expect(within(card).queryByText(/Guest stars/i)).not.toBeInTheDocument();
  });

  it("Emby movies section shows Jellyfin/Emby CommunityRating label when instance exists", async () => {
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

    fireEvent.click(screen.getByRole("tab", { name: "Emby" }));
    await waitFor(() => expect(screen.getByTestId("pruner-provider-tab-emby")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Cleanup" }));
    await waitFor(() => expect(screen.getByTestId("pruner-provider-movies-config-emby")).toBeInTheDocument());
    const movies = screen.getByTestId("pruner-provider-movies-config-emby");
    expect(within(movies).getByText(/community rating/i)).toBeInTheDocument();
    expect(within(movies).queryByText(/Plex audienceRating/i)).not.toBeInTheDocument();
  });

  it("Emby Schedule sub-tab shows TV/Movies schedule cards when no instances exist", async () => {
    const client = new QueryClient();
    client.setQueryData(qk.me, adminUser);
    vi.spyOn(prunerApi, "fetchPrunerInstances").mockResolvedValue([]);
    vi.spyOn(prunerApi, "fetchPrunerJobsInspection").mockResolvedValue({ jobs: [], default_recent_slice: true });

    render(wrap(<PrunerInstancesListPage />, client));

    await waitFor(() => expect(screen.getByTestId("pruner-top-level-tabs")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("tab", { name: "Emby" }));
    fireEvent.click(screen.getByRole("button", { name: "Schedule" }));
    await waitFor(() => expect(screen.getByTestId("pruner-provider-schedule-wrap")).toBeInTheDocument());
    expect(screen.queryByTestId("pruner-provider-schedule-hint")).not.toBeInTheDocument();
    expect(screen.getAllByText(/Enter a number of seconds/i).length).toBeGreaterThanOrEqual(2);
    await waitFor(() => expect(screen.getByTestId("pruner-schedule-row-emby-tv")).toBeInTheDocument());
    expect(screen.getByTestId("pruner-schedule-row-emby-movies")).toBeInTheDocument();
    const tvCard = screen.getByTestId("pruner-schedule-row-emby-tv");
    expect(within(tvCard).getByText("TV automatic cleanup")).toBeInTheDocument();
    expect(within(tvCard).getByText(/saved criteria from the Cleanup tab/i)).toBeInTheDocument();
  });

  it("each provider Schedule sub-tab renders TV and Movies schedule rows when instances exist", async () => {
    const client = new QueryClient();
    client.setQueryData(qk.me, adminUser);
    const scope = (media_scope: "tv" | "movies") => ({
      media_scope,
      missing_primary_media_reported_enabled: true,
      never_played_stale_reported_enabled: false,
      never_played_min_age_days: 90,
      watched_tv_reported_enabled: false,
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
    });
    vi.spyOn(prunerApi, "fetchPrunerInstances").mockResolvedValue([
      {
        id: 1,
        provider: "emby",
        display_name: "Emby Home",
        base_url: "http://emby",
        enabled: true,
        last_connection_test_at: null,
        last_connection_test_ok: null,
        last_connection_test_detail: null,
        scopes: [scope("tv"), scope("movies")],
      },
      {
        id: 2,
        provider: "jellyfin",
        display_name: "JF Home",
        base_url: "http://jf",
        enabled: true,
        last_connection_test_at: null,
        last_connection_test_ok: null,
        last_connection_test_detail: null,
        scopes: [scope("tv"), scope("movies")],
      },
      {
        id: 3,
        provider: "plex",
        display_name: "Plex Home",
        base_url: "http://plex",
        enabled: true,
        last_connection_test_at: null,
        last_connection_test_ok: null,
        last_connection_test_detail: null,
        scopes: [scope("tv"), scope("movies")],
      },
    ]);
    vi.spyOn(prunerApi, "fetchPrunerJobsInspection").mockResolvedValue({ jobs: [], default_recent_slice: true });

    render(wrap(<PrunerInstancesListPage />, client));

    await waitFor(() => expect(screen.getByTestId("pruner-top-level-tabs")).toBeInTheDocument());
    for (const label of ["Emby", "Jellyfin", "Plex"] as const) {
      fireEvent.click(screen.getByRole("tab", { name: label }));
      fireEvent.click(screen.getByRole("button", { name: "Schedule" }));
      const p = label.toLowerCase();
      await waitFor(() => expect(screen.getByTestId(`pruner-schedule-row-${p}-tv`)).toBeInTheDocument());
      expect(screen.getByTestId(`pruner-schedule-row-${p}-movies`)).toBeInTheDocument();
    }
  });

  it("Emby Schedule sub-tab save PATCHes scheduled_preview_enabled and scheduled_preview_interval_seconds", async () => {
    const csrfSpy = vi.spyOn(authApi, "fetchCsrfToken").mockResolvedValue("csrf-test");
    const patchSpy = vi.spyOn(prunerApi, "patchPrunerScope").mockResolvedValue({} as never);
    const client = new QueryClient();
    client.setQueryData(qk.me, adminUser);
    const scope = (media_scope: "tv" | "movies") => ({
      media_scope,
      missing_primary_media_reported_enabled: true,
      never_played_stale_reported_enabled: false,
      never_played_min_age_days: 90,
      watched_tv_reported_enabled: false,
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
    });
    vi.spyOn(prunerApi, "fetchPrunerInstances").mockResolvedValue([
      {
        id: 1,
        provider: "emby",
        display_name: "Emby Home",
        base_url: "http://emby",
        enabled: true,
        last_connection_test_at: null,
        last_connection_test_ok: null,
        last_connection_test_detail: null,
        scopes: [scope("tv"), scope("movies")],
      },
      {
        id: 2,
        provider: "jellyfin",
        display_name: "JF Home",
        base_url: "http://jf",
        enabled: true,
        last_connection_test_at: null,
        last_connection_test_ok: null,
        last_connection_test_detail: null,
        scopes: [scope("tv"), scope("movies")],
      },
      {
        id: 3,
        provider: "plex",
        display_name: "Plex Home",
        base_url: "http://plex",
        enabled: true,
        last_connection_test_at: null,
        last_connection_test_ok: null,
        last_connection_test_detail: null,
        scopes: [scope("tv"), scope("movies")],
      },
    ]);
    vi.spyOn(prunerApi, "fetchPrunerJobsInspection").mockResolvedValue({ jobs: [], default_recent_slice: true });

    render(wrap(<PrunerInstancesListPage />, client));

    await waitFor(() => expect(screen.getByTestId("pruner-top-level-tabs")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("tab", { name: "Emby" }));
    fireEvent.click(screen.getByRole("button", { name: "Schedule" }));
    await waitFor(() => expect(screen.getByTestId("pruner-schedule-row-emby-tv")).toBeInTheDocument());

    const embyTv = screen.getByTestId("pruner-schedule-row-emby-tv");
    fireEvent.click(within(embyTv).getByRole("radio", { name: "On" }));
    fireEvent.change(within(embyTv).getByLabelText("Run every interval in seconds"), { target: { value: "120" } });
    fireEvent.click(within(embyTv).getByRole("button", { name: /Save TV schedule/i }));

    await waitFor(() => {
      expect(patchSpy).toHaveBeenCalledWith(
        1,
        "tv",
        expect.objectContaining({
          scheduled_preview_enabled: true,
          scheduled_preview_interval_seconds: 120,
          preview_max_items: 500,
          csrf_token: "csrf-test",
        }),
      );
    });

    csrfSpy.mockRestore();
    patchSpy.mockRestore();
  });

  it("Overview shows At a glance cards without connection forms", async () => {
    const client = new QueryClient();
    vi.spyOn(prunerApi, "fetchPrunerInstances").mockResolvedValue([]);
    vi.spyOn(prunerApi, "fetchPrunerJobsInspection").mockResolvedValue({ jobs: [], default_recent_slice: true });

    render(wrap(<PrunerInstancesListPage />, client));

    await waitFor(() => expect(screen.getByTestId("pruner-overview-at-a-glance")).toBeInTheDocument());
    expect(screen.getByText(/At a glance/i)).toBeInTheDocument();
    expect(screen.queryByTestId("pruner-connection-panel-emby")).not.toBeInTheDocument();
  });
});
