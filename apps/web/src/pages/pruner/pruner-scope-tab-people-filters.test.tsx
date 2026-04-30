import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import * as authApi from "../../lib/api/auth-api";
import { qk } from "../../lib/auth/queries";
import * as prunerApi from "../../lib/pruner/api";
import type { UserPublic } from "../../lib/api/types";
import type { PrunerServerInstance } from "../../lib/pruner/api";
import { PrunerInstanceShell } from "./pruner-instance-shell";
import { PrunerScopeTab } from "./pruner-scope-tab";

const operator: UserPublic = { id: 1, username: "alice", role: "admin" };

const jf: PrunerServerInstance = {
  id: 61,
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
      preview_include_people: ["Ada Lovelace"],
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
};

describe("PrunerScopeTab people filters", () => {
  it("saves preview_include_people via scope PATCH and shows Jellyfin note", async () => {
    const csrfSpy = vi
      .spyOn(authApi, "fetchCsrfToken")
      .mockResolvedValue("csrf-test");
    const spyRuns = vi
      .spyOn(prunerApi, "fetchPrunerPreviewRuns")
      .mockResolvedValue([]);
    const spyInst = vi
      .spyOn(prunerApi, "fetchPrunerInstance")
      .mockResolvedValue(jf);
    const spyPatch = vi.spyOn(prunerApi, "patchPrunerScope").mockResolvedValue({
      ...jf.scopes[0],
      preview_include_people: ["Ada Lovelace", "Grace Hopper"],
    });
    try {
      const qc = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });
      qc.setQueryData(qk.me, operator);
      qc.setQueryData(["pruner", "instances", 61], jf);

      const router = createMemoryRouter(
        [
          {
            path: "/instances/:instanceId",
            element: <PrunerInstanceShell />,
            children: [{ path: "tv", element: <PrunerScopeTab scope="tv" /> }],
          },
        ],
        { initialEntries: ["/instances/61/tv"] },
      );

      render(
        <QueryClientProvider client={qc}>
          <RouterProvider router={router} />
        </QueryClientProvider>,
      );

      await waitFor(() =>
        expect(
          screen.getByTestId("pruner-people-filters-panel"),
        ).toBeInTheDocument(),
      );
      expect(
        screen.getByTestId("pruner-people-jf-emby-note"),
      ).toBeInTheDocument();
      expect(
        screen.queryByTestId("pruner-people-plex-note"),
      ).not.toBeInTheDocument();
      const input = screen.getByPlaceholderText(/Alex Carter/i);
      fireEvent.change(input, {
        target: { value: "Ada Lovelace, Grace Hopper" },
      });
      fireEvent.click(
        screen.getByRole("button", { name: /save people filters/i }),
      );
      await waitFor(() => {
        expect(spyPatch).toHaveBeenCalledWith(
          61,
          "tv",
          expect.objectContaining({
            preview_include_people: ["Ada Lovelace", "Grace Hopper"],
            preview_include_people_roles: [],
          }),
        );
      });
    } finally {
      csrfSpy.mockRestore();
      spyRuns.mockRestore();
      spyInst.mockRestore();
      spyPatch.mockRestore();
    }
  });

  it("shows Plex-specific people note on Plex instances", async () => {
    const plex: PrunerServerInstance = {
      id: 62,
      provider: "plex",
      display_name: "Plex",
      base_url: "http://plex:32400",
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
    };
    const spyRuns = vi
      .spyOn(prunerApi, "fetchPrunerPreviewRuns")
      .mockResolvedValue([]);
    const spyInst = vi
      .spyOn(prunerApi, "fetchPrunerInstance")
      .mockResolvedValue(plex);
    try {
      const qc = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });
      qc.setQueryData(qk.me, operator);
      qc.setQueryData(["pruner", "instances", 62], plex);

      const router = createMemoryRouter(
        [
          {
            path: "/instances/:instanceId",
            element: <PrunerInstanceShell />,
            children: [{ path: "tv", element: <PrunerScopeTab scope="tv" /> }],
          },
        ],
        { initialEntries: ["/instances/62/tv"] },
      );

      render(
        <QueryClientProvider client={qc}>
          <RouterProvider router={router} />
        </QueryClientProvider>,
      );

      await waitFor(() =>
        expect(
          screen.getByTestId("pruner-people-plex-note"),
        ).toBeInTheDocument(),
      );
      expect(screen.getByTestId("pruner-people-plex-note").textContent).toMatch(
        /Role|Writer|Director|allLeaves/i,
      );
      expect(
        screen.queryByTestId("pruner-people-jf-emby-note"),
      ).not.toBeInTheDocument();
    } finally {
      spyRuns.mockRestore();
      spyInst.mockRestore();
    }
  });
});
