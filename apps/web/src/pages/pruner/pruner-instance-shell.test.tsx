import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import * as prunerQueries from "../../lib/pruner/queries";
import { PrunerInstanceShell } from "./pruner-instance-shell";

describe("PrunerInstanceShell", () => {
  it("keeps instance-first navigation with Movies/TV as secondary tabs", async () => {
    vi.spyOn(prunerQueries, "usePrunerInstanceQuery").mockReturnValue({
      isLoading: false,
      isError: false,
      error: null,
      data: {
        id: 9,
        provider: "plex",
        display_name: "Plex Home",
        base_url: "http://plex:32400",
        enabled: true,
        last_connection_test_at: null,
        last_connection_test_ok: null,
        last_connection_test_detail: null,
        scopes: [],
      },
    } as never);

    const router = createMemoryRouter(
      [
        {
          path: "/instances/:instanceId/*",
          element: <PrunerInstanceShell />,
          children: [
            { path: "overview", element: <div>Overview content</div> },
          ],
        },
      ],
      { initialEntries: ["/instances/9/overview"] },
    );

    render(
      <QueryClientProvider client={new QueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    await waitFor(() =>
      expect(
        screen.getByTestId("pruner-instance-section-tabs"),
      ).toBeInTheDocument(),
    );
    const tabs = screen.getByTestId("pruner-instance-section-tabs");
    expect(tabs.textContent).toMatch(/Overview/);
    expect(tabs.textContent).toMatch(/Movies/);
    expect(tabs.textContent).toMatch(/TV/);
    expect(tabs.textContent).toMatch(/Connection/);
    expect(screen.getByRole("link", { name: "Movies" })).toHaveAttribute(
      "href",
      "/pruner/instances/9/movies",
    );
    expect(screen.getByRole("link", { name: "TV" })).toHaveAttribute(
      "href",
      "/pruner/instances/9/tv",
    );
    expect(
      screen.getByTestId("pruner-instance-shell").textContent ?? "",
    ).toMatch(/Emby, Jellyfin, and Plex/i);
  });
});
