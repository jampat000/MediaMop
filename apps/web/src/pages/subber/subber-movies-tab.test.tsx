import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as subberQueries from "../../lib/subber/subber-queries";
import { SubberMoviesTab } from "./subber-movies-tab";

function wrap(ui: ReactNode, client: QueryClient) {
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("SubberMoviesTab", () => {
  const mutate = vi.fn();

  afterEach(() => {
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    vi.spyOn(subberQueries, "useSubberSettingsQuery").mockReturnValue({
      data: { language_preferences: ["en"] } as ReturnType<typeof subberQueries.useSubberSettingsQuery>["data"],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberSettingsQuery>);
    vi.spyOn(subberQueries, "useSubberLibraryMoviesQuery").mockReturnValue({
      data: {
        movies: [
          {
            file_path: "/m.mkv",
            movie_title: "Inception",
            movie_year: 2010,
            languages: [{ state_id: 2, language_code: "en", status: "missing", subtitle_path: null, last_searched_at: null, search_count: 0, source: null }],
          },
        ],
      },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberLibraryMoviesQuery>);
    vi.spyOn(subberQueries, "useSubberSearchNowMutation").mockReturnValue({
      mutate,
      isPending: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberSearchNowMutation>);
    vi.spyOn(subberQueries, "useSubberSearchAllMissingMoviesMutation").mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberSearchAllMissingMoviesMutation>);
  });

  it("renders movie row and Search now", async () => {
    const client = new QueryClient();
    render(wrap(<SubberMoviesTab canOperate />, client));
    await waitFor(() => expect(screen.getByText(/Inception/)).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("subber-movies-search-now"));
    expect(mutate).toHaveBeenCalledWith(2);
  });

  it("shows empty state", async () => {
    vi.spyOn(subberQueries, "useSubberLibraryMoviesQuery").mockReturnValue({
      data: { movies: [] },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberLibraryMoviesQuery>);
    const client = new QueryClient();
    render(wrap(<SubberMoviesTab canOperate={false} />, client));
    await waitFor(() => expect(screen.getByTestId("subber-movies-empty")).toBeInTheDocument());
  });
});
