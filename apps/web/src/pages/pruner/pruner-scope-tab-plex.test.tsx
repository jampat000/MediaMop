import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { qk } from "../../lib/auth/queries";
import * as prunerApi from "../../lib/pruner/api";
import type { UserPublic } from "../../lib/api/types";
import type { PrunerServerInstance } from "../../lib/pruner/api";
import {
  RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
  RULE_FAMILY_WATCHED_TV_REPORTED,
} from "../../lib/pruner/api";
import { PrunerInstanceShell } from "./pruner-instance-shell";
import { PrunerScopeTab } from "./pruner-scope-tab";

const operator: UserPublic = { id: 1, username: "alice", role: "admin" };

const plexInstance: PrunerServerInstance = {
  id: 9,
  provider: "plex",
  display_name: "Plex Home",
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
      watched_movie_low_rating_max_community_rating: 4,
      unwatched_movie_stale_reported_enabled: false,
      unwatched_movie_stale_min_age_days: 90,
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
      watched_movies_reported_enabled: false,
      watched_movie_low_rating_reported_enabled: false,
      watched_movie_low_rating_max_community_rating: 4,
      unwatched_movie_stale_reported_enabled: false,
      unwatched_movie_stale_min_age_days: 90,
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

describe("PrunerScopeTab (Plex)", () => {
  it("uses preview-first flow for missing primary: queue enabled, no live-only surface, other rules called out", async () => {
    const spy = vi.spyOn(prunerApi, "fetchPrunerPreviewRuns").mockResolvedValue([]);
    const spyInst = vi.spyOn(prunerApi, "fetchPrunerInstance").mockResolvedValue(plexInstance);
    try {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      qc.setQueryData(qk.me, operator);
      qc.setQueryData(["pruner", "instances", 9], plexInstance);

      const router = createMemoryRouter(
        [
          {
            path: "/instances/:instanceId",
            element: <PrunerInstanceShell />,
            children: [{ path: "tv", element: <PrunerScopeTab scope="tv" /> }],
          },
        ],
        { initialEntries: ["/instances/9/tv"] },
      );

      render(
        <QueryClientProvider client={qc}>
          <RouterProvider router={router} />
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId("pruner-plex-other-rules-note")).toBeInTheDocument();
      });
      expect(screen.queryByTestId("pruner-plex-live-surface")).not.toBeInTheDocument();
      expect(screen.getByTestId("pruner-plex-genre-empty-preview-note")).toBeInTheDocument();
      expect(screen.getByTestId("pruner-plex-genre-empty-preview-note").textContent).toMatch(/zero rows/i);
      expect(screen.getByTestId("pruner-plex-other-rules-note").textContent).toMatch(
        /never-played|watched|low-rating|unwatched stale/i,
      );
      const btn = screen.getByRole("button", { name: /queue preview \(missing primary art\)/i });
      expect(btn).not.toBeDisabled();
    } finally {
      spy.mockRestore();
      spyInst.mockRestore();
    }
  });

  it("shows apply-from-preview for Plex only when snapshot is missing-primary success with candidates", async () => {
    const runId = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
    const spy = vi.spyOn(prunerApi, "fetchPrunerPreviewRuns").mockResolvedValue([
      {
        preview_run_id: runId,
        server_instance_id: 9,
        media_scope: "tv",
        rule_family_id: RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
        pruner_job_id: 1,
        candidate_count: 2,
        truncated: false,
        outcome: "success",
        unsupported_detail: null,
        error_message: null,
        created_at: new Date().toISOString(),
      },
    ]);
    const spyInst = vi.spyOn(prunerApi, "fetchPrunerInstance").mockResolvedValue(plexInstance);
    try {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      qc.setQueryData(qk.me, operator);
      qc.setQueryData(["pruner", "instances", 9], plexInstance);

      const router = createMemoryRouter(
        [
          {
            path: "/instances/:instanceId",
            element: <PrunerInstanceShell />,
            children: [{ path: "tv", element: <PrunerScopeTab scope="tv" /> }],
          },
        ],
        { initialEntries: ["/instances/9/tv"] },
      );

      render(
        <QueryClientProvider client={qc}>
          <RouterProvider router={router} />
        </QueryClientProvider>,
      );

      await waitFor(() => expect(screen.getByTestId(`pruner-apply-open-${runId}`)).toBeInTheDocument());
    } finally {
      spy.mockRestore();
      spyInst.mockRestore();
    }
  });

  it("Plex: never_played_stale_reported and watched_tv_reported preview rows stay unsupported (no apply)", async () => {
    const neverId = "bbbbbbbb-bbbb-cccc-dddd-eeeeeeeeeeee";
    const watchedId = "cccccccc-bbbb-cccc-dddd-eeeeeeeeeeee";
    const spy = vi.spyOn(prunerApi, "fetchPrunerPreviewRuns").mockResolvedValue([
      {
        preview_run_id: neverId,
        server_instance_id: 9,
        media_scope: "tv",
        rule_family_id: "never_played_stale_reported",
        pruner_job_id: 2,
        candidate_count: 0,
        truncated: false,
        outcome: "unsupported",
        unsupported_detail:
          "Plex: never-played stale library candidacy is not implemented on MediaMop (Jellyfin/Emby only for this rule).",
        error_message: null,
        created_at: new Date().toISOString(),
      },
      {
        preview_run_id: watchedId,
        server_instance_id: 9,
        media_scope: "tv",
        rule_family_id: RULE_FAMILY_WATCHED_TV_REPORTED,
        pruner_job_id: 3,
        candidate_count: 0,
        truncated: false,
        outcome: "unsupported",
        unsupported_detail:
          "Plex: watched TV preview is not implemented on MediaMop in this release (Jellyfin/Emby only).",
        error_message: null,
        created_at: new Date().toISOString(),
      },
    ]);
    const spyInst = vi.spyOn(prunerApi, "fetchPrunerInstance").mockResolvedValue(plexInstance);
    try {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      qc.setQueryData(qk.me, operator);
      qc.setQueryData(["pruner", "instances", 9], plexInstance);

      const router = createMemoryRouter(
        [
          {
            path: "/instances/:instanceId",
            element: <PrunerInstanceShell />,
            children: [{ path: "tv", element: <PrunerScopeTab scope="tv" /> }],
          },
        ],
        { initialEntries: ["/instances/9/tv"] },
      );

      render(
        <QueryClientProvider client={qc}>
          <RouterProvider router={router} />
        </QueryClientProvider>,
      );

      await waitFor(() => expect(screen.getByText("Stale never-played")).toBeInTheDocument());
      await waitFor(() => expect(screen.getByText("Watched TV (episodes)")).toBeInTheDocument());
      expect(screen.getByText(/never-played stale library candidacy is not implemented/i)).toBeInTheDocument();
      expect(screen.getByText(/watched TV preview is not implemented/i)).toBeInTheDocument();
      expect(screen.queryByTestId(`pruner-apply-open-${neverId}`)).not.toBeInTheDocument();
      expect(screen.queryByTestId(`pruner-apply-open-${watchedId}`)).not.toBeInTheDocument();
    } finally {
      spy.mockRestore();
      spyInst.mockRestore();
    }
  });

  it("shows Plex missing-primary preview cap note for operators", async () => {
    const spy = vi.spyOn(prunerApi, "fetchPrunerPreviewRuns").mockResolvedValue([]);
    const spyInst = vi.spyOn(prunerApi, "fetchPrunerInstance").mockResolvedValue(plexInstance);
    try {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      qc.setQueryData(qk.me, operator);
      qc.setQueryData(["pruner", "instances", 9], plexInstance);

      const router = createMemoryRouter(
        [
          {
            path: "/instances/:instanceId",
            element: <PrunerInstanceShell />,
            children: [{ path: "tv", element: <PrunerScopeTab scope="tv" /> }],
          },
        ],
        { initialEntries: ["/instances/9/tv"] },
      );

      render(
        <QueryClientProvider client={qc}>
          <RouterProvider router={router} />
        </QueryClientProvider>,
      );

      await waitFor(() => expect(screen.getByTestId("pruner-plex-preview-cap-note")).toBeInTheDocument());
      const note = screen.getByTestId("pruner-plex-preview-cap-note").textContent ?? "";
      expect(note).toMatch(/MEDIAMOP_PRUNER_PLEX_LIVE_ABS_MAX_ITEMS/);
      expect(note).toMatch(/500/);
      expect(note).toMatch(/truncated/i);
    } finally {
      spy.mockRestore();
      spyInst.mockRestore();
    }
  });

  it("does not render Jellyfin-only never-played panel for Plex", async () => {
    const spy = vi.spyOn(prunerApi, "fetchPrunerPreviewRuns").mockResolvedValue([]);
    const spyInst = vi.spyOn(prunerApi, "fetchPrunerInstance").mockResolvedValue(plexInstance);
    try {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      qc.setQueryData(qk.me, operator);
      qc.setQueryData(["pruner", "instances", 9], plexInstance);

      const router = createMemoryRouter(
        [
          {
            path: "/instances/:instanceId",
            element: <PrunerInstanceShell />,
            children: [{ path: "tv", element: <PrunerScopeTab scope="tv" /> }],
          },
        ],
        { initialEntries: ["/instances/9/tv"] },
      );

      render(
        <QueryClientProvider client={qc}>
          <RouterProvider router={router} />
        </QueryClientProvider>,
      );

      await waitFor(() => expect(screen.getByTestId("pruner-plex-other-rules-note")).toBeInTheDocument());
      expect(screen.queryByTestId("pruner-never-played-stale-panel")).not.toBeInTheDocument();
    } finally {
      spy.mockRestore();
      spyInst.mockRestore();
    }
  });
});
