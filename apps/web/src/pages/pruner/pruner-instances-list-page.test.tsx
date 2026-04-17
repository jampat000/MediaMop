import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { UserPublic } from "../../lib/api/types";
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
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders top-level tabs Overview, Connections, Emby, Jellyfin, Plex, Schedules, Jobs", async () => {
    const client = new QueryClient();
    vi.spyOn(prunerApi, "fetchPrunerInstances").mockResolvedValue([]);
    vi.spyOn(prunerApi, "fetchPrunerJobsInspection").mockResolvedValue({ jobs: [], default_recent_slice: true });

    render(wrap(<PrunerInstancesListPage />, client));

    await waitFor(() => expect(screen.getByTestId("pruner-top-level-tabs")).toBeInTheDocument());
    const tabs = screen.getByTestId("pruner-top-level-tabs");
    expect(tabs.textContent).toMatch(/Overview/);
    expect(tabs.textContent).toMatch(/Connections/);
    expect(tabs.textContent).toMatch(/Emby/);
    expect(tabs.textContent).toMatch(/Jellyfin/);
    expect(tabs.textContent).toMatch(/Plex/);
    expect(tabs.textContent).toMatch(/Schedules/);
    expect(tabs.textContent).toMatch(/Jobs/);
  });

  it("Connections tab renders Base URL and credential fields for all three providers without a registered instance", async () => {
    const client = new QueryClient();
    vi.spyOn(prunerApi, "fetchPrunerInstances").mockResolvedValue([]);
    vi.spyOn(prunerApi, "fetchPrunerJobsInspection").mockResolvedValue({ jobs: [], default_recent_slice: true });
    vi.spyOn(prunerApi, "postPrunerInstance").mockResolvedValue({
      id: 11,
      provider: "emby",
      display_name: "Emby",
      base_url: "http://emby.local",
      enabled: true,
      last_connection_test_at: null,
      last_connection_test_ok: null,
      last_connection_test_detail: null,
      scopes: [],
    });

    render(wrap(<PrunerInstancesListPage />, client));

    await waitFor(() => expect(screen.getByTestId("pruner-top-level-tabs")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("tab", { name: "Connections" }));
    await waitFor(() => expect(screen.getByTestId("pruner-connections-tab")).toBeInTheDocument());

    expect(screen.getByTestId("pruner-connection-panel-emby")).toBeInTheDocument();
    expect(screen.getByTestId("pruner-connection-panel-jellyfin")).toBeInTheDocument();
    expect(screen.getByTestId("pruner-connection-panel-plex")).toBeInTheDocument();
    expect(screen.getAllByLabelText(/Base URL/i)).toHaveLength(3);
    expect(screen.getAllByLabelText(/API key/i).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByLabelText(/Token/i)).toBeInTheDocument();
    expect(screen.queryByTestId("pruner-provider-configuration-emby")).not.toBeInTheDocument();
  });

  it("Plex connection form uses Token label, not API key", async () => {
    const client = new QueryClient();
    vi.spyOn(prunerApi, "fetchPrunerInstances").mockResolvedValue([]);
    vi.spyOn(prunerApi, "fetchPrunerJobsInspection").mockResolvedValue({ jobs: [], default_recent_slice: true });

    render(wrap(<PrunerInstancesListPage />, client));

    fireEvent.click(screen.getByRole("tab", { name: "Connections" }));
    await waitFor(() => expect(screen.getByTestId("pruner-connection-panel-plex")).toBeInTheDocument());
    const plexPanel = screen.getByTestId("pruner-connection-panel-plex");
    expect(within(plexPanel).getByLabelText(/Token/i)).toBeInTheDocument();
    expect(within(plexPanel).queryByLabelText(/^API key$/i)).not.toBeInTheDocument();
  });

  it("Emby tab shows Rules sub-navigation, TV/Movies columns, and no nested top-level tabs inside the workspace", async () => {
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
    expect(screen.getByRole("button", { name: "Rules" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Filters" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "People" })).toBeInTheDocument();
    const rulesCard = screen.getByTestId("pruner-provider-configuration-emby");
    expect(within(rulesCard).getByRole("heading", { level: 3, name: /^Rules$/i })).toBeInTheDocument();
    expect(within(rulesCard).getAllByText(/^TV$/).length).toBeGreaterThanOrEqual(1);
    expect(within(rulesCard).getAllByText(/^Movies$/).length).toBeGreaterThanOrEqual(1);
    expect(rulesCard).toBeInTheDocument();
    expect(within(rulesCard).queryByRole("tab")).toBeNull();
    expect(within(rulesCard).queryByRole("checkbox")).toBeNull();
    expect(screen.queryByRole("button", { name: /Save watched TV rule/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save TV rules" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save Movies rules" })).toBeInTheDocument();
    expect(screen.getByTestId("pruner-rules-dry-run-tv-btn")).toBeInTheDocument();
    expect(screen.getByTestId("pruner-rules-dry-run-movies-btn")).toBeInTheDocument();
  });

  it("People sub-tab shows TV and Movies name textareas and dry run buttons", async () => {
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
    fireEvent.click(screen.getByRole("button", { name: "People" }));
    await waitFor(() => expect(screen.getByTestId("pruner-provider-people-card-emby")).toBeInTheDocument());
    const peopleCard = screen.getByTestId("pruner-provider-people-card-emby");
    expect(within(peopleCard).getAllByPlaceholderText(/Alex Carter/i)).toHaveLength(2);
    expect(screen.getByTestId("pruner-people-dry-run-tv-btn")).toBeInTheDocument();
    expect(screen.getByTestId("pruner-people-dry-run-movies-btn")).toBeInTheDocument();
  });

  it("pre-connection Emby tab shows disabled configuration controls, not missing", async () => {
    const client = new QueryClient();
    vi.spyOn(prunerApi, "fetchPrunerInstances").mockResolvedValue([]);
    vi.spyOn(prunerApi, "fetchPrunerJobsInspection").mockResolvedValue({ jobs: [], default_recent_slice: true });

    render(wrap(<PrunerInstancesListPage />, client));

    fireEvent.click(screen.getByRole("tab", { name: "Emby" }));
    await waitFor(() => expect(screen.getByTestId("pruner-provider-configuration-emby")).toBeInTheDocument());
    expect(screen.getByText(/Save a connection first to enable these settings/i)).toBeInTheDocument();
    const disabledFieldsets = screen.getByTestId("pruner-provider-configuration-emby").querySelectorAll("fieldset[disabled]");
    expect(disabledFieldsets.length).toBe(2);
    expect(screen.getByText(/Watched TV removal/i)).toBeInTheDocument();
  });

  it("Plex provider tab shows TV and Movies sections with unsupported rules and missing-primary filter scope note", async () => {
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
    expect(screen.getByTestId("pruner-provider-plex-tv-unsupported-rules")).toBeInTheDocument();
    expect(screen.getAllByText(/Not supported for Plex/i).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByTestId("pruner-plex-tv-filters-scope-note")).toBeInTheDocument();
    expect(screen.getAllByTestId("pruner-plex-other-rules-note").length).toBeGreaterThanOrEqual(1);
    const moviesSection = screen.getByTestId("pruner-provider-movies-config-plex");
    expect(within(moviesSection).getByText(/Plex audienceRating/i)).toBeInTheDocument();
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
    await waitFor(() => expect(screen.getByTestId("pruner-provider-movies-config-emby")).toBeInTheDocument());
    const movies = screen.getByTestId("pruner-provider-movies-config-emby");
    expect(within(movies).getByText(/Jellyfin\/Emby CommunityRating/i)).toBeInTheDocument();
    expect(within(movies).queryByText(/Plex audienceRating/i)).not.toBeInTheDocument();
  });

  it("Schedules tab shows empty state when no instances exist", async () => {
    const client = new QueryClient();
    client.setQueryData(qk.me, adminUser);
    vi.spyOn(prunerApi, "fetchPrunerInstances").mockResolvedValue([]);
    vi.spyOn(prunerApi, "fetchPrunerJobsInspection").mockResolvedValue({ jobs: [], default_recent_slice: true });

    render(wrap(<PrunerInstancesListPage />, client));

    await waitFor(() => expect(screen.getByTestId("pruner-top-level-tabs")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("tab", { name: "Schedules" }));
    await waitFor(() => expect(screen.getByTestId("pruner-schedules-empty-state")).toBeInTheDocument());
    expect(screen.getByText(/Register a provider under Connections to enable schedules/i)).toBeInTheDocument();
  });

  it("Schedules tab renders six schedule rows grouped by provider when instances exist", async () => {
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
    fireEvent.click(screen.getByRole("tab", { name: "Schedules" }));
    await waitFor(() => expect(screen.getByTestId("pruner-schedule-row-emby-tv")).toBeInTheDocument());
    expect(screen.getByTestId("pruner-schedule-row-emby-movies")).toBeInTheDocument();
    expect(screen.getByTestId("pruner-schedule-row-jellyfin-tv")).toBeInTheDocument();
    expect(screen.getByTestId("pruner-schedule-row-jellyfin-movies")).toBeInTheDocument();
    expect(screen.getByTestId("pruner-schedule-row-plex-tv")).toBeInTheDocument();
    expect(screen.getByTestId("pruner-schedule-row-plex-movies")).toBeInTheDocument();
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
