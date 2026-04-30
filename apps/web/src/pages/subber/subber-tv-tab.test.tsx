import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as subberQueries from "../../lib/subber/subber-queries";
import { SubberTvTab } from "./subber-tv-tab";

function wrap(ui: ReactNode, client: QueryClient) {
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("SubberTvTab", () => {
  const mutate = vi.fn();

  afterEach(() => {
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    vi.spyOn(subberQueries, "useSubberSettingsQuery").mockReturnValue({
      data: { language_preferences: ["en", "fr"] } as ReturnType<
        typeof subberQueries.useSubberSettingsQuery
      >["data"],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberSettingsQuery>);
    vi.spyOn(subberQueries, "useSubberLibraryTvQuery").mockReturnValue({
      data: {
        shows: [
          {
            show_title: "Demo",
            seasons: [
              {
                season_number: 1,
                episodes: [
                  {
                    file_path: "/d.mkv",
                    episode_number: 1,
                    episode_title: "Pilot",
                    languages: [
                      {
                        state_id: 7,
                        language_code: "en",
                        status: "found",
                        subtitle_path: null,
                        last_searched_at: null,
                        search_count: 0,
                        source: null,
                      },
                      {
                        state_id: 8,
                        language_code: "fr",
                        status: "missing",
                        subtitle_path: null,
                        last_searched_at: null,
                        search_count: 0,
                        source: null,
                      },
                    ],
                  },
                ],
              },
            ],
          },
        ],
        total: 1,
      },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberLibraryTvQuery>);
    vi.spyOn(subberQueries, "useSubberSearchNowMutation").mockReturnValue({
      mutate,
      isPending: false,
    } as unknown as ReturnType<
      typeof subberQueries.useSubberSearchNowMutation
    >);
    vi.spyOn(
      subberQueries,
      "useSubberSearchAllMissingTvMutation",
    ).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<
      typeof subberQueries.useSubberSearchAllMissingTvMutation
    >);
  });

  it("renders episode and Search now triggers mutation", async () => {
    const client = new QueryClient();
    render(wrap(<SubberTvTab canOperate />, client));
    await waitFor(() => expect(screen.getByText(/Demo/)).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("subber-tv-search-now"));
    expect(mutate).toHaveBeenCalledWith(8);
  });

  it("shows empty state when no shows", async () => {
    vi.spyOn(subberQueries, "useSubberLibraryTvQuery").mockReturnValue({
      data: { shows: [], total: 0 },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberLibraryTvQuery>);
    const client = new QueryClient();
    render(wrap(<SubberTvTab canOperate={false} />, client));
    await waitFor(() =>
      expect(screen.getByTestId("subber-tv-empty")).toBeInTheDocument(),
    );
  });
});
