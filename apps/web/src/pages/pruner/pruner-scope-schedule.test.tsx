import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { UserPublic } from "../../lib/api/types";
import { qk } from "../../lib/auth/queries";
import type { PrunerServerInstance } from "../../lib/pruner/api";
import * as prunerApi from "../../lib/pruner/api";
import { PrunerInstanceShell } from "./pruner-instance-shell";
import { PrunerScopeTab } from "./pruner-scope-tab";

const operator: UserPublic = { id: 1, username: "alice", role: "admin" };

function scopeRow(media_scope: "tv" | "movies") {
  return {
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
    scheduled_preview_hours_limited: false,
    scheduled_preview_days: "",
    scheduled_preview_start: "00:00",
    scheduled_preview_end: "23:59",
    last_scheduled_preview_enqueued_at: null,
    last_preview_run_uuid: null,
    last_preview_at: null,
    last_preview_candidate_count: null,
    last_preview_outcome: null,
    last_preview_error: null,
  };
}

const embyInstance: PrunerServerInstance = {
  id: 3,
  provider: "emby",
  display_name: "Home Emby",
  base_url: "http://emby-sched.test",
  enabled: true,
  last_connection_test_at: null,
  last_connection_test_ok: null,
  last_connection_test_detail: null,
  scopes: [scopeRow("tv"), scopeRow("movies")],
};

describe("PrunerScopeTab scheduled preview", () => {
  it("shows per-tab schedule controls without a global shortcut", async () => {
    const spyRuns = vi.spyOn(prunerApi, "fetchPrunerPreviewRuns").mockResolvedValue([]);
    const spyInst = vi.spyOn(prunerApi, "fetchPrunerInstance").mockResolvedValue(embyInstance);
    try {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      qc.setQueryData(qk.me, operator);

      const router = createMemoryRouter(
        [
          {
            path: "/instances/:instanceId",
            element: <PrunerInstanceShell />,
            children: [{ path: "tv", element: <PrunerScopeTab scope="tv" /> }],
          },
        ],
        { initialEntries: ["/instances/3/tv"] },
      );

      render(
        <QueryClientProvider client={qc}>
          <RouterProvider router={router} />
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId("pruner-scope-scheduled-preview")).toBeInTheDocument();
      });
      const block = screen.getByTestId("pruner-scope-scheduled-preview");
      expect(block.textContent).toMatch(/TV shows/i);
      expect(block.textContent).not.toMatch(/both scopes/i);
      expect(screen.getByRole("button", { name: /save tv schedule/i })).toBeInTheDocument();
    } finally {
      spyRuns.mockRestore();
      spyInst.mockRestore();
    }
  });
});
