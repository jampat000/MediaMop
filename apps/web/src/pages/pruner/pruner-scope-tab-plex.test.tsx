import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { qk } from "../../lib/auth/queries";
import * as prunerApi from "../../lib/pruner/api";
import type { UserPublic } from "../../lib/api/types";
import type { PrunerServerInstance } from "../../lib/pruner/api";
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
      preview_max_items: 500,
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
      preview_max_items: 500,
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
  it("shows live-only Plex messaging, gates surface, and disables preview queue", async () => {
    const spy = vi.spyOn(prunerApi, "fetchPrunerPreviewRuns").mockResolvedValue([]);
    const spyInst = vi.spyOn(prunerApi, "fetchPrunerInstance").mockResolvedValue(plexInstance);
    const spyPlexElig = vi.spyOn(prunerApi, "fetchPrunerPlexLiveEligibility").mockResolvedValue({
      eligible: false,
      reasons: ["Plex live gate off (MEDIAMOP_PRUNER_PLEX_LIVE_REMOVAL_ENABLED=0)."],
      apply_feature_enabled: false,
      plex_live_feature_enabled: false,
      server_instance_id: 9,
      media_scope: "tv",
      provider: "plex",
      display_name: "Plex Home",
      rule_family_id: "missing_primary_media_reported",
      rule_enabled: true,
      live_max_items_cap: 50,
      required_confirmation_phrase: "PLEX BROKEN LIBRARY LIVE CONFIRM",
    });
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
        expect(screen.getByRole("status")).toBeInTheDocument();
      });
      expect(screen.getByRole("status").textContent).toMatch(/no preview/i);
      expect(screen.getByRole("status").textContent).toMatch(/live/i);
      expect(screen.getByTestId("pruner-plex-live-surface")).toBeInTheDocument();
      const liveBtn = screen.getByTestId("pruner-plex-live-open");
      expect(liveBtn).toBeDisabled();
      const btn = screen.getByRole("button", { name: /queue preview \(missing primary art\)/i });
      expect(btn).toBeDisabled();
    } finally {
      spy.mockRestore();
      spyInst.mockRestore();
      spyPlexElig.mockRestore();
    }
  });

  it("requires both acknowledgements and exact phrase before Plex live confirm", async () => {
    const spy = vi.spyOn(prunerApi, "fetchPrunerPreviewRuns").mockResolvedValue([]);
    const spyInst = vi.spyOn(prunerApi, "fetchPrunerInstance").mockResolvedValue(plexInstance);
    const phrase = "PLEX BROKEN LIBRARY LIVE CONFIRM";
    const spyPlexElig = vi.spyOn(prunerApi, "fetchPrunerPlexLiveEligibility").mockResolvedValue({
      eligible: true,
      reasons: [],
      apply_feature_enabled: true,
      plex_live_feature_enabled: true,
      server_instance_id: 9,
      media_scope: "tv",
      provider: "plex",
      display_name: "Plex Home",
      rule_family_id: "missing_primary_media_reported",
      rule_enabled: true,
      live_max_items_cap: 3,
      required_confirmation_phrase: phrase,
    });
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

      await waitFor(() => expect(screen.getByTestId("pruner-plex-live-open")).not.toBeDisabled());
      fireEvent.click(screen.getByTestId("pruner-plex-live-open"));

      await waitFor(() => expect(screen.getByTestId("pruner-plex-live-modal")).toBeInTheDocument());

      const confirm = screen.getByTestId("pruner-plex-live-confirm");
      expect(confirm).toBeDisabled();

      fireEvent.click(screen.getByTestId("pruner-plex-live-ack-no-preview"));
      fireEvent.click(screen.getByTestId("pruner-plex-live-ack-live"));
      fireEvent.change(screen.getByTestId("pruner-plex-live-phrase"), { target: { value: "wrong" } });
      expect(confirm).toBeDisabled();

      fireEvent.change(screen.getByTestId("pruner-plex-live-phrase"), { target: { value: phrase } });
      expect(confirm).not.toBeDisabled();
    } finally {
      spy.mockRestore();
      spyInst.mockRestore();
      spyPlexElig.mockRestore();
    }
  });
});
