import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import * as prunerApi from "../../lib/pruner/api";
import { PrunerInstancesListPage } from "./pruner-instances-list-page";

function wrap(ui: ReactNode, client: QueryClient) {
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("PrunerInstancesListPage", () => {
  it("lists instances from API", async () => {
    const client = new QueryClient();
    vi.spyOn(prunerApi, "fetchPrunerInstances").mockResolvedValue([
      {
        id: 2,
        provider: "emby",
        display_name: "Home",
        base_url: "http://emby.test",
        enabled: true,
        last_connection_test_at: null,
        last_connection_test_ok: null,
        last_connection_test_detail: null,
        scopes: [],
      },
    ]);

    render(wrap(<PrunerInstancesListPage />, client));

    await waitFor(() => {
      expect(screen.getByText("Home")).toBeInTheDocument();
    });
    expect(screen.getByRole("link", { name: /open workspace/i })).toHaveAttribute("href", "/app/pruner/instances/2/overview");
    expect(screen.getByTestId("pruner-instances-list")).toBeInTheDocument();
  });
});
