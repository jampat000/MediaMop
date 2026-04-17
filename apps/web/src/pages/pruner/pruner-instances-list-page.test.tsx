import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  it("renders top-level Pruner tabs Overview/Emby/Jellyfin/Plex/Schedules/Jobs", async () => {
    const client = new QueryClient();
    vi.spyOn(prunerApi, "fetchPrunerInstances").mockResolvedValue([]);
    vi.spyOn(prunerApi, "fetchPrunerJobsInspection").mockResolvedValue({ jobs: [], default_recent_slice: true });

    render(wrap(<PrunerInstancesListPage />, client));

    await waitFor(() => expect(screen.getByTestId("pruner-top-level-tabs")).toBeInTheDocument());
    const tabs = screen.getByTestId("pruner-top-level-tabs");
    expect(tabs.textContent).toMatch(/Overview/);
    expect(tabs.textContent).toMatch(/Emby/);
    expect(tabs.textContent).toMatch(/Jellyfin/);
    expect(tabs.textContent).toMatch(/Plex/);
    expect(tabs.textContent).toMatch(/Schedules/);
    expect(tabs.textContent).toMatch(/Jobs/);
  });

  it("provider tab shows Overview/Movies/TV/Connection even without registered instance", async () => {
    const client = new QueryClient();
    vi.spyOn(prunerApi, "fetchPrunerInstances").mockResolvedValue([]);
    vi.spyOn(prunerApi, "fetchPrunerJobsInspection").mockResolvedValue({ jobs: [], default_recent_slice: true });

    render(wrap(<PrunerInstancesListPage />, client));

    await waitFor(() => expect(screen.getByTestId("pruner-top-level-tabs")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Emby" }));
    await waitFor(() => expect(screen.getByTestId("pruner-provider-tab-emby")).toBeInTheDocument());
    const providerTabs = screen.getByTestId("pruner-provider-sections-emby");
    expect(providerTabs.textContent).toMatch(/Overview/);
    expect(providerTabs.textContent).toMatch(/Movies/);
    expect(providerTabs.textContent).toMatch(/TV/);
    expect(providerTabs.textContent).toMatch(/Connection/);
    expect(screen.getByTestId("pruner-provider-setup-needed-emby-overview").textContent ?? "").toMatch(
      /setup needed/i,
    );

    fireEvent.click(screen.getByRole("button", { name: "Movies" }));
    expect(screen.getByTestId("pruner-provider-setup-needed-emby-movies").textContent ?? "").toMatch(/setup needed/i);
  });

  it("shows provider-first zero-instance framing with Emby, Jellyfin, and Plex named", async () => {
    const client = new QueryClient();
    vi.spyOn(prunerApi, "fetchPrunerInstances").mockResolvedValue([]);
    vi.spyOn(prunerApi, "fetchPrunerJobsInspection").mockResolvedValue({ jobs: [], default_recent_slice: true });

    render(wrap(<PrunerInstancesListPage />, client));

    await waitFor(() => expect(screen.getByTestId("pruner-empty-state")).toBeInTheDocument());
    const page = screen.getByTestId("pruner-scope-page");
    expect(page.textContent).toContain("Emby");
    expect(page.textContent).toContain("Jellyfin");
    expect(page.textContent).toContain("Plex");
    expect(screen.getByTestId("pruner-empty-state").textContent ?? "").toMatch(/nothing is shared across providers/i);
  });

  it("lists provider instances and keeps provider-scoped sections", async () => {
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
    vi.spyOn(prunerApi, "fetchPrunerJobsInspection").mockResolvedValue({ jobs: [], default_recent_slice: true });

    render(wrap(<PrunerInstancesListPage />, client));

    fireEvent.click(screen.getByRole("button", { name: "Emby" }));
    await waitFor(() => expect(screen.getByTestId("pruner-provider-tab-emby")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Movies" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "TV" })).toBeInTheDocument();
    expect(screen.queryByTestId("pruner-provider-setup-needed-emby-overview")).not.toBeInTheDocument();
  });
});
