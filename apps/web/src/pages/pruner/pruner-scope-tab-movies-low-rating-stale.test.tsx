import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { qk } from "../../lib/auth/queries";
import * as authApi from "../../lib/api/auth-api";
import * as prunerApi from "../../lib/pruner/api";
import type { UserPublic } from "../../lib/api/types";
import type { PrunerServerInstance } from "../../lib/pruner/api";
import {
  RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED,
  RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED,
} from "../../lib/pruner/api";
import { PrunerInstanceShell } from "./pruner-instance-shell";
import { PrunerScopeTab } from "./pruner-scope-tab";

const operator: UserPublic = { id: 1, username: "alice", role: "admin" };

const jellyfinMovies: PrunerServerInstance = {
  id: 44,
  provider: "jellyfin",
  display_name: "JF",
  base_url: "http://jf:8096",
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
};

describe("PrunerScopeTab Movies / low-rating and unwatched stale", () => {
  it("queues previews with watched_movie_low_rating_reported and unwatched_movie_stale_reported", async () => {
    const spyRuns = vi
      .spyOn(prunerApi, "fetchPrunerPreviewRuns")
      .mockResolvedValue([]);
    const spyInst = vi
      .spyOn(prunerApi, "fetchPrunerInstance")
      .mockResolvedValue(jellyfinMovies);
    const spyPreview = vi
      .spyOn(prunerApi, "postPrunerPreview")
      .mockResolvedValue({ pruner_job_id: 902 });
    try {
      const qc = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });
      qc.setQueryData(qk.me, operator);
      qc.setQueryData(["pruner", "instances", 44], jellyfinMovies);

      const router = createMemoryRouter(
        [
          {
            path: "/instances/:instanceId",
            element: <PrunerInstanceShell />,
            children: [
              { path: "movies", element: <PrunerScopeTab scope="movies" /> },
            ],
          },
        ],
        { initialEntries: ["/instances/44/movies"] },
      );

      render(
        <QueryClientProvider client={qc}>
          <RouterProvider router={router} />
        </QueryClientProvider>,
      );

      await waitFor(() =>
        expect(
          screen.getByTestId("pruner-watched-low-rating-panel"),
        ).toBeInTheDocument(),
      );
      fireEvent.click(
        screen.getByRole("button", {
          name: /Scan for low-score watched movies/i,
        }),
      );
      await waitFor(() => {
        expect(spyPreview).toHaveBeenCalledWith(44, "movies", {
          rule_family_id: RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED,
        });
      });
      fireEvent.click(
        screen.getByRole("button", { name: /Scan for old unwatched movies/i }),
      );
      await waitFor(() => {
        expect(spyPreview).toHaveBeenCalledWith(44, "movies", {
          rule_family_id: RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED,
        });
      });
    } finally {
      spyRuns.mockRestore();
      spyInst.mockRestore();
      spyPreview.mockRestore();
    }
  });

  it("saves low-rating ceiling using Jellyfin/Emby CommunityRating field only (not Plex audienceRating)", async () => {
    vi.spyOn(authApi, "fetchCsrfToken").mockResolvedValue("csrf-test");
    const spyPatch = vi
      .spyOn(prunerApi, "patchPrunerScope")
      .mockResolvedValue(jellyfinMovies.scopes[1]!);
    const spyRuns = vi
      .spyOn(prunerApi, "fetchPrunerPreviewRuns")
      .mockResolvedValue([]);
    const spyInst = vi
      .spyOn(prunerApi, "fetchPrunerInstance")
      .mockResolvedValue(jellyfinMovies);
    try {
      const qc = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });
      qc.setQueryData(qk.me, operator);
      qc.setQueryData(["pruner", "instances", 44], jellyfinMovies);

      const router = createMemoryRouter(
        [
          {
            path: "/instances/:instanceId",
            element: <PrunerInstanceShell />,
            children: [
              { path: "movies", element: <PrunerScopeTab scope="movies" /> },
            ],
          },
        ],
        { initialEntries: ["/instances/44/movies"] },
      );

      render(
        <QueryClientProvider client={qc}>
          <RouterProvider router={router} />
        </QueryClientProvider>,
      );

      await waitFor(() =>
        expect(
          screen.getByTestId("pruner-watched-low-rating-panel"),
        ).toBeInTheDocument(),
      );
      fireEvent.click(
        screen.getByRole("button", { name: /save low-rating rule/i }),
      );
      await waitFor(() => expect(spyPatch).toHaveBeenCalled());
      const body = spyPatch.mock.calls[0]![2] as Record<string, unknown>;
      expect(
        body.watched_movie_low_rating_max_jellyfin_emby_community_rating,
      ).toBe(4);
      expect(
        Object.prototype.hasOwnProperty.call(
          body,
          "watched_movie_low_rating_max_plex_audience_rating",
        ),
      ).toBe(false);
    } finally {
      spyPatch.mockRestore();
      spyRuns.mockRestore();
      spyInst.mockRestore();
    }
  });
});
