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

function scopeBase(overrides: Partial<PrunerServerInstance["scopes"][0]> = {}) {
  return {
    media_scope: "tv" as const,
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
    ...overrides,
  };
}

const jellyfin: PrunerServerInstance = {
  id: 71,
  provider: "jellyfin",
  display_name: "JF",
  base_url: "http://jf:8096",
  enabled: true,
  last_connection_test_at: null,
  last_connection_test_ok: null,
  last_connection_test_detail: null,
  scopes: [scopeBase({ media_scope: "tv" }), scopeBase({ media_scope: "movies" })],
};

const plex: PrunerServerInstance = {
  id: 72,
  provider: "plex",
  display_name: "Plex",
  base_url: "http://plex:32400",
  enabled: true,
  last_connection_test_at: null,
  last_connection_test_ok: null,
  last_connection_test_detail: null,
  scopes: [scopeBase({ media_scope: "tv" }), scopeBase({ media_scope: "movies" })],
};

describe("PrunerScopeTab year / studio / collection preview filters", () => {
  it("Jellyfin: saves year bounds and studio list; hides Plex-only collection panel", async () => {
    vi.spyOn(authApi, "fetchCsrfToken").mockResolvedValue("csrf-test");
    vi.spyOn(prunerApi, "fetchPrunerPreviewRuns").mockResolvedValue([]);
    vi.spyOn(prunerApi, "fetchPrunerInstance").mockResolvedValue(jellyfin);
    const spyPatch = vi.spyOn(prunerApi, "patchPrunerScope").mockResolvedValue({
      ...jellyfin.scopes[0],
      preview_year_min: 2010,
      preview_year_max: 2020,
      preview_include_studios: ["Acme"],
    });
    try {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      qc.setQueryData(qk.me, operator);
      qc.setQueryData(["pruner", "instances", 71], jellyfin);

      const router = createMemoryRouter(
        [
          {
            path: "/instances/:instanceId",
            element: <PrunerInstanceShell />,
            children: [{ path: "tv", element: <PrunerScopeTab scope="tv" /> }],
          },
        ],
        { initialEntries: ["/instances/71/tv"] },
      );

      render(
        <QueryClientProvider client={qc}>
          <RouterProvider router={router} />
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId("pruner-year-filters-panel")).toBeInTheDocument();
      });
      expect(screen.queryByTestId("pruner-collection-preview-panel")).toBeNull();

      fireEvent.change(screen.getByRole("spinbutton", { name: /min year/i }), { target: { value: "2010" } });
      fireEvent.change(screen.getByRole("spinbutton", { name: /max year/i }), { target: { value: "2020" } });
      fireEvent.click(screen.getByRole("button", { name: /save year bounds/i }));

      await waitFor(() => {
        expect(spyPatch).toHaveBeenCalledWith(
          71,
          "tv",
          expect.objectContaining({
            preview_year_min: 2010,
            preview_year_max: 2020,
            csrf_token: "csrf-test",
          }),
        );
      });

      fireEvent.change(screen.getByPlaceholderText(/warner bros/i), { target: { value: "Acme" } });
      fireEvent.click(screen.getByRole("button", { name: /save studio filters/i }));

      await waitFor(() => {
        expect(spyPatch).toHaveBeenCalledWith(
          71,
          "tv",
          expect.objectContaining({
            preview_include_studios: ["Acme"],
            csrf_token: "csrf-test",
          }),
        );
      });
    } finally {
      vi.restoreAllMocks();
    }
  });

  it("Plex: shows collection preview panel and saves collection tokens", async () => {
    vi.spyOn(authApi, "fetchCsrfToken").mockResolvedValue("csrf-test");
    vi.spyOn(prunerApi, "fetchPrunerPreviewRuns").mockResolvedValue([]);
    vi.spyOn(prunerApi, "fetchPrunerInstance").mockResolvedValue(plex);
    const spyPatch = vi.spyOn(prunerApi, "patchPrunerScope").mockResolvedValue({
      ...plex.scopes[0],
      preview_include_collections: ["MCU"],
    });
    try {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      qc.setQueryData(qk.me, operator);
      qc.setQueryData(["pruner", "instances", 72], plex);

      const router = createMemoryRouter(
        [
          {
            path: "/instances/:instanceId",
            element: <PrunerInstanceShell />,
            children: [{ path: "tv", element: <PrunerScopeTab scope="tv" /> }],
          },
        ],
        { initialEntries: ["/instances/72/tv"] },
      );

      render(
        <QueryClientProvider client={qc}>
          <RouterProvider router={router} />
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId("pruner-collection-preview-panel")).toBeInTheDocument();
      });
      expect(screen.getByText(/Jellyfin\/Emby previews do/i)).toBeInTheDocument();

      fireEvent.change(screen.getByPlaceholderText(/marvel cinematic/i), { target: { value: "MCU" } });
      fireEvent.click(screen.getByRole("button", { name: /save collection filters/i }));

      await waitFor(() => {
        expect(spyPatch).toHaveBeenCalledWith(
          72,
          "tv",
          expect.objectContaining({
            preview_include_collections: ["MCU"],
            csrf_token: "csrf-test",
          }),
        );
      });
    } finally {
      vi.restoreAllMocks();
    }
  });

  it("rejects non-integer year input before PATCH", async () => {
    vi.spyOn(authApi, "fetchCsrfToken").mockResolvedValue("csrf-test");
    vi.spyOn(prunerApi, "fetchPrunerPreviewRuns").mockResolvedValue([]);
    vi.spyOn(prunerApi, "fetchPrunerInstance").mockResolvedValue(jellyfin);
    const spyPatch = vi.spyOn(prunerApi, "patchPrunerScope");
    try {
      const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      qc.setQueryData(qk.me, operator);
      qc.setQueryData(["pruner", "instances", 71], jellyfin);

      const router = createMemoryRouter(
        [
          {
            path: "/instances/:instanceId",
            element: <PrunerInstanceShell />,
            children: [{ path: "tv", element: <PrunerScopeTab scope="tv" /> }],
          },
        ],
        { initialEntries: ["/instances/71/tv"] },
      );

      render(
        <QueryClientProvider client={qc}>
          <RouterProvider router={router} />
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId("pruner-year-filters-panel")).toBeInTheDocument();
      });

      fireEvent.change(screen.getByRole("spinbutton", { name: /min year/i }), { target: { value: "20.5" } });
      fireEvent.click(screen.getByRole("button", { name: /save year bounds/i }));

      await waitFor(() => {
        expect(screen.getByText(/whole number between 1900 and 2100/i)).toBeInTheDocument();
      });
      expect(spyPatch).not.toHaveBeenCalled();
    } finally {
      vi.restoreAllMocks();
    }
  });
});
