import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { qk } from "../../lib/auth/queries";
import type { UserPublic } from "../../lib/api/types";
import * as prunerApi from "../../lib/pruner/api";
import type { PrunerPreviewRunSummary, PrunerServerInstance } from "../../lib/pruner/api";
import { PRUNER_REMOVE_BROKEN_LIBRARY_ENTRIES_LABEL } from "../../lib/pruner/api";
import { PrunerInstanceShell } from "./pruner-instance-shell";
import { PrunerScopeTab } from "./pruner-scope-tab";

const operator: UserPublic = { id: 1, username: "alice", role: "admin" };

const runId = "11111111-1111-4111-8111-111111111111";

const jellyfinInstance: PrunerServerInstance = {
  id: 2,
  provider: "jellyfin",
  display_name: "JF Home",
  base_url: "http://jf:8096",
  enabled: true,
  last_connection_test_at: null,
  last_connection_test_ok: null,
  last_connection_test_detail: null,
  scopes: [
    {
      media_scope: "tv",
      missing_primary_media_reported_enabled: true,
      preview_max_items: 500,
      scheduled_preview_enabled: false,
      scheduled_preview_interval_seconds: 3600,
      last_scheduled_preview_enqueued_at: null,
      last_preview_run_uuid: runId,
      last_preview_at: null,
      last_preview_candidate_count: 2,
      last_preview_outcome: "success",
      last_preview_error: null,
    },
    {
      media_scope: "movies",
      missing_primary_media_reported_enabled: true,
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

const previewRun: PrunerPreviewRunSummary = {
  preview_run_id: runId,
  server_instance_id: 2,
  media_scope: "tv",
  rule_family_id: "missing_primary_media_reported",
  pruner_job_id: 1,
  candidate_count: 2,
  truncated: false,
  outcome: "success",
  unsupported_detail: null,
  error_message: null,
  created_at: "2026-04-17T12:00:00.000Z",
};

const embyInstance: PrunerServerInstance = {
  ...jellyfinInstance,
  id: 3,
  provider: "emby",
  display_name: "Emby Home",
  base_url: "http://em:8096",
};

describe("PrunerScopeTab apply (Jellyfin)", () => {
  it("exposes Remove broken library entries only on preview history for Jellyfin success rows", async () => {
    const spyElig = vi.spyOn(prunerApi, "fetchPrunerApplyEligibility").mockResolvedValue({
      eligible: true,
      reasons: [],
      apply_feature_enabled: true,
      preview_run_id: runId,
      server_instance_id: 2,
      media_scope: "tv",
      provider: "jellyfin",
      display_name: "JF Home",
      preview_created_at: previewRun.created_at,
      candidate_count: 2,
      preview_outcome: "success",
      rule_family_id: "missing_primary_media_reported",
    });
    try {
      const qc = new QueryClient({
        defaultOptions: { queries: { retry: false, staleTime: 60_000, refetchOnMount: false } },
      });
      qc.setQueryData(qk.me, operator);
      await qc.prefetchQuery({
        queryKey: ["pruner", "instances", 2],
        queryFn: async () => jellyfinInstance,
      });
      await qc.prefetchQuery({
        queryKey: ["pruner", "preview-runs", 2, "tv"],
        queryFn: async () => [previewRun],
      });

      const router = createMemoryRouter(
        [
          {
            path: "/instances/:instanceId",
            element: <PrunerInstanceShell />,
            children: [{ path: "tv", element: <PrunerScopeTab scope="tv" /> }],
          },
        ],
        { initialEntries: ["/instances/2/tv"] },
      );

      render(
        <QueryClientProvider client={qc}>
          <RouterProvider router={router} />
        </QueryClientProvider>,
      );

      await waitFor(() => {
        expect(screen.getByTestId("pruner-preview-runs-history")).toBeInTheDocument();
      });

      const openBtn = screen.getByTestId(`pruner-apply-open-${runId}`);
      expect(openBtn.textContent).toBe(PRUNER_REMOVE_BROKEN_LIBRARY_ENTRIES_LABEL);

      fireEvent.click(openBtn);

      await waitFor(() => {
        expect(screen.getByTestId("pruner-apply-modal")).toBeInTheDocument();
      });

      const titles = screen.getAllByText(PRUNER_REMOVE_BROKEN_LIBRARY_ENTRIES_LABEL);
      expect(titles.length).toBeGreaterThanOrEqual(2);
    } finally {
      spyElig.mockRestore();
    }
  });

  it("does not show apply on Emby preview rows (Jellyfin-only slice)", async () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 60_000, refetchOnMount: false } },
    });
    qc.setQueryData(qk.me, operator);
    await qc.prefetchQuery({
      queryKey: ["pruner", "instances", 3],
      queryFn: async () => embyInstance,
    });
    await qc.prefetchQuery({
      queryKey: ["pruner", "preview-runs", 3, "tv"],
      queryFn: async () => [{ ...previewRun, server_instance_id: 3 }],
    });

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
      expect(screen.getByTestId("pruner-preview-runs-history")).toBeInTheDocument();
    });

    expect(screen.queryByTestId(`pruner-apply-open-${runId}`)).toBeNull();
  });
});
