import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { qk } from "../../lib/auth/queries";
import * as prunerApi from "../../lib/pruner/api";
import type { UserPublic } from "../../lib/api/types";
import type { PrunerServerInstance } from "../../lib/pruner/api";
import { RULE_FAMILY_WATCHED_MOVIES_REPORTED } from "../../lib/pruner/api";
import { PrunerInstanceShell } from "./pruner-instance-shell";
import { PrunerScopeTab } from "./pruner-scope-tab";

const operator: UserPublic = { id: 1, username: "alice", role: "admin" };

const jellyfinMovies: PrunerServerInstance = {
  id: 22,
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
      preview_max_items: 500,
      preview_include_genres: [],
      preview_include_people: [],
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
      watched_movies_reported_enabled: true,
      preview_max_items: 500,
      preview_include_genres: [],
      preview_include_people: [],
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

describe("PrunerScopeTab Movies / watched movies", () => {
  it("shows Jellyfin/Emby watched-movies panel and queues preview with watched_movies_reported", async () => {
    const spyRuns = vi.spyOn(prunerApi, "fetchPrunerPreviewRuns").mockResolvedValue([]);
    const spyInst = vi.spyOn(prunerApi, "fetchPrunerInstance").mockResolvedValue(jellyfinMovies);
    const spyPreview = vi.spyOn(prunerApi, "postPrunerPreview").mockResolvedValue({ pruner_job_id: 901 });
    try {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      qc.setQueryData(qk.me, operator);
      qc.setQueryData(["pruner", "instances", 22], jellyfinMovies);

      const router = createMemoryRouter(
        [
          {
            path: "/instances/:instanceId",
            element: <PrunerInstanceShell />,
            children: [{ path: "movies", element: <PrunerScopeTab scope="movies" /> }],
          },
        ],
        { initialEntries: ["/instances/22/movies"] },
      );

      render(
        <QueryClientProvider client={qc}>
          <RouterProvider router={router} />
        </QueryClientProvider>,
      );

      await waitFor(() => expect(screen.getByTestId("pruner-watched-movies-panel")).toBeInTheDocument());
      fireEvent.click(screen.getByRole("button", { name: /queue preview \(watched movies\)/i }));
      await waitFor(() => {
        expect(spyPreview).toHaveBeenCalledWith(22, "movies", {
          rule_family_id: RULE_FAMILY_WATCHED_MOVIES_REPORTED,
        });
      });
    } finally {
      spyRuns.mockRestore();
      spyInst.mockRestore();
      spyPreview.mockRestore();
    }
  });
});
