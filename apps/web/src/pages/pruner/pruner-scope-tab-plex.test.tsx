import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
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
      preview_max_items: 500,
      last_preview_run_uuid: null,
      last_preview_at: null,
      last_preview_candidate_count: null,
      last_preview_outcome: null,
      last_preview_error: null,
    },
    {
      media_scope: "movies",
      missing_primary_media_reported_enabled: true,
      preview_max_items: 500,
      last_preview_run_uuid: null,
      last_preview_at: null,
      last_preview_candidate_count: null,
      last_preview_outcome: null,
      last_preview_error: null,
    },
  ],
};

describe("PrunerScopeTab (Plex)", () => {
  it("shows explicit unsupported messaging and disables preview queue", async () => {
    const spy = vi.spyOn(prunerApi, "fetchPrunerPreviewRuns").mockResolvedValue([]);
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
      expect(screen.getByRole("status").textContent).toMatch(/not supported/i);
      const btn = screen.getByRole("button", { name: /queue preview job/i });
      expect(btn).toBeDisabled();
    } finally {
      spy.mockRestore();
    }
  });
});
