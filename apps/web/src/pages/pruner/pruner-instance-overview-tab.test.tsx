import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { Outlet, createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { PrunerServerInstance } from "../../lib/pruner/api";
import { PrunerInstanceOverviewTab } from "./pruner-instance-overview-tab";

const baseScopeTv = {
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
  preview_include_genres: ["Drama"],
  preview_include_people: [],
  preview_year_min: null,
  preview_year_max: null,
  preview_include_studios: ["Acme"],
  preview_include_collections: [],
  scheduled_preview_enabled: false,
  scheduled_preview_interval_seconds: 3600,
  last_scheduled_preview_enqueued_at: null,
  last_preview_run_uuid: "550e8400-e29b-41d4-a716-446655440000",
  last_preview_at: "2026-04-17T12:00:00.000Z",
  last_preview_candidate_count: 3,
  last_preview_outcome: "success",
  last_preview_error: null,
};

const baseScopeMovies = {
  media_scope: "movies",
  missing_primary_media_reported_enabled: true,
  never_played_stale_reported_enabled: false,
  never_played_min_age_days: 90,
  watched_tv_reported_enabled: false,
  watched_movies_reported_enabled: true,
  watched_movie_low_rating_reported_enabled: false,
  watched_movie_low_rating_max_jellyfin_emby_community_rating: 4,
  watched_movie_low_rating_max_plex_audience_rating: 4,
  unwatched_movie_stale_reported_enabled: false,
  unwatched_movie_stale_min_age_days: 90,
  preview_max_items: 500,
  preview_include_genres: [],
  preview_include_people: ["Pat Example"],
  preview_year_min: 2000,
  preview_year_max: 2020,
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
};

const jellyfinInstance: PrunerServerInstance = {
  id: 77,
  provider: "jellyfin",
  display_name: "JF Lab",
  base_url: "http://jf:8096",
  enabled: true,
  last_connection_test_at: null,
  last_connection_test_ok: null,
  last_connection_test_detail: null,
  scopes: [{ ...baseScopeTv }, { ...baseScopeMovies }],
};

const plexInstance: PrunerServerInstance = {
  id: 88,
  provider: "plex",
  display_name: "Plex Lab",
  base_url: "http://plex:32400",
  enabled: true,
  last_connection_test_at: null,
  last_connection_test_ok: null,
  last_connection_test_detail: null,
  scopes: [
    { ...baseScopeTv, media_scope: "tv" },
    { ...baseScopeMovies, media_scope: "movies" },
  ],
};

function OverviewLayout({ instance }: { instance: PrunerServerInstance }) {
  return <Outlet context={{ instanceId: instance.id, instance }} />;
}

describe("PrunerInstanceOverviewTab", () => {
  it("renders TV and Movies cards with active rules, filter counts, and last preview for Jellyfin", async () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const router = createMemoryRouter(
      [
        {
          path: "/instances/:instanceId",
          element: <OverviewLayout instance={jellyfinInstance} />,
          children: [
            { path: "overview", element: <PrunerInstanceOverviewTab /> },
          ],
        },
      ],
      { initialEntries: ["/instances/77/overview"] },
    );

    render(
      <QueryClientProvider client={qc}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    await waitFor(() =>
      expect(
        screen.getByTestId("pruner-instance-overview"),
      ).toBeInTheDocument(),
    );
    expect(screen.getByTestId("pruner-overview-scope-tv")).toBeInTheDocument();
    expect(
      screen.getByTestId("pruner-overview-scope-movies"),
    ).toBeInTheDocument();
    expect(screen.getByText(/Delete watched TV episodes/)).toBeInTheDocument();
    const tvCard = screen.getByTestId("pruner-overview-scope-tv");
    expect(tvCard.textContent).toMatch(/success/);
    expect(tvCard.textContent).toMatch(/2026/);
    expect(tvCard.textContent).toMatch(/Automatic previews are off/i);
    expect(
      screen.getByRole("link", { name: /open activity/i }),
    ).toHaveAttribute("href", "/activity");
    expect(
      screen.getByText(
        /Removed, skipped, and failed counts for each cleanup run/i,
      ),
    ).toBeInTheDocument();
  });

  it("shows Plex-only unsupported callouts on the TV scope card", async () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const router = createMemoryRouter(
      [
        {
          path: "/instances/:instanceId",
          element: <OverviewLayout instance={plexInstance} />,
          children: [
            { path: "overview", element: <PrunerInstanceOverviewTab /> },
          ],
        },
      ],
      { initialEntries: ["/instances/88/overview"] },
    );

    render(
      <QueryClientProvider client={qc}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    await waitFor(() =>
      expect(
        screen.getByTestId("pruner-overview-scope-tv"),
      ).toBeInTheDocument(),
    );
    const tvCard = screen.getByTestId("pruner-overview-scope-tv");
    expect(tvCard.textContent).toMatch(/Not available for this Plex library/i);
    expect(tvCard.textContent).toMatch(/Watched TV episodes/i);
  });
});
