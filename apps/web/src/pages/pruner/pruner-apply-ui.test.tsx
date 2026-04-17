import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { qk } from "../../lib/auth/queries";
import type { UserPublic } from "../../lib/api/types";
import * as prunerApi from "../../lib/pruner/api";
import type { PrunerPreviewRunSummary, PrunerServerInstance } from "../../lib/pruner/api";
import {
  PRUNER_REMOVE_BROKEN_LIBRARY_ENTRIES_LABEL,
  PRUNER_REMOVE_STALE_NEVER_PLAYED_LIBRARY_ENTRIES_LABEL,
} from "../../lib/pruner/api";
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
      never_played_stale_reported_enabled: false,
      never_played_min_age_days: 90,
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

describe("PrunerScopeTab apply (Jellyfin + Emby preview → apply)", () => {
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
      apply_operator_label: PRUNER_REMOVE_BROKEN_LIBRARY_ENTRIES_LABEL,
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

      const modal = await screen.findByTestId("pruner-apply-modal");
      await waitFor(() => {
        expect(within(modal).getByRole("heading", { level: 3 })).toHaveTextContent(
          PRUNER_REMOVE_BROKEN_LIBRARY_ENTRIES_LABEL,
        );
      });

      const titles = screen.getAllByText(PRUNER_REMOVE_BROKEN_LIBRARY_ENTRIES_LABEL);
      expect(titles.length).toBeGreaterThanOrEqual(2);
    } finally {
      spyElig.mockRestore();
    }
  });

  it("exposes Remove broken library entries for eligible Emby preview history rows", async () => {
    const spyElig = vi.spyOn(prunerApi, "fetchPrunerApplyEligibility").mockResolvedValue({
      eligible: true,
      reasons: [],
      apply_feature_enabled: true,
      preview_run_id: runId,
      server_instance_id: 3,
      media_scope: "tv",
      provider: "emby",
      display_name: "Emby Home",
      preview_created_at: previewRun.created_at,
      candidate_count: 2,
      preview_outcome: "success",
      rule_family_id: "missing_primary_media_reported",
      apply_operator_label: PRUNER_REMOVE_BROKEN_LIBRARY_ENTRIES_LABEL,
    });
    try {
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
        expect(screen.getByTestId(`pruner-apply-open-${runId}`)).toBeInTheDocument();
      });
    } finally {
      spyElig.mockRestore();
    }
  });

  it("uses Remove stale never-played library entries for never-played preview rows", async () => {
    const neverRunId = "22222222-2222-4222-8222-222222222222";
    const spyElig = vi.spyOn(prunerApi, "fetchPrunerApplyEligibility").mockResolvedValue({
      eligible: true,
      reasons: [],
      apply_feature_enabled: true,
      preview_run_id: neverRunId,
      server_instance_id: 2,
      media_scope: "tv",
      provider: "jellyfin",
      display_name: "JF Home",
      preview_created_at: previewRun.created_at,
      candidate_count: 1,
      preview_outcome: "success",
      rule_family_id: "never_played_stale_reported",
      apply_operator_label: PRUNER_REMOVE_STALE_NEVER_PLAYED_LIBRARY_ENTRIES_LABEL,
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
        queryFn: async () => [
          previewRun,
          {
            ...previewRun,
            preview_run_id: neverRunId,
            rule_family_id: "never_played_stale_reported",
            candidate_count: 1,
          },
        ],
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
        expect(screen.getByTestId(`pruner-apply-open-${neverRunId}`)).toBeInTheDocument();
      });
      const openBtn = screen.getByTestId(`pruner-apply-open-${neverRunId}`);
      expect(openBtn.textContent).toBe(PRUNER_REMOVE_STALE_NEVER_PLAYED_LIBRARY_ENTRIES_LABEL);
      fireEvent.click(openBtn);
      const modal = await screen.findByTestId("pruner-apply-modal");
      await waitFor(() => {
        expect(within(modal).getByRole("heading", { level: 3 })).toHaveTextContent(
          PRUNER_REMOVE_STALE_NEVER_PLAYED_LIBRARY_ENTRIES_LABEL,
        );
      });
    } finally {
      spyElig.mockRestore();
    }
  });

  it("does not show apply on Plex preview rows", async () => {
    const plexInstance: PrunerServerInstance = {
      id: 4,
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
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 60_000, refetchOnMount: false } },
    });
    qc.setQueryData(qk.me, operator);
    await qc.prefetchQuery({
      queryKey: ["pruner", "instances", 4],
      queryFn: async () => plexInstance,
    });
    await qc.prefetchQuery({
      queryKey: ["pruner", "preview-runs", 4, "tv"],
      queryFn: async () => [{ ...previewRun, server_instance_id: 4 }],
    });

    const router = createMemoryRouter(
      [
        {
          path: "/instances/:instanceId",
          element: <PrunerInstanceShell />,
          children: [{ path: "tv", element: <PrunerScopeTab scope="tv" /> }],
        },
      ],
      { initialEntries: ["/instances/4/tv"] },
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
