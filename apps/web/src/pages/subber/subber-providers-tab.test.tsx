import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as authApi from "../../lib/api/auth-api";
import * as subberQueries from "../../lib/subber/subber-queries";
import { SubberProvidersTab } from "./subber-providers-tab";

function wrap(ui: ReactNode, client: QueryClient) {
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("SubberProvidersTab", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    vi.spyOn(authApi, "fetchCsrfToken").mockResolvedValue("csrf");
    vi.spyOn(subberQueries, "useSubberTestOpensubtitlesMutation").mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue({ ok: true, message: "ok" }),
      isPending: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberTestOpensubtitlesMutation>);
    vi.spyOn(subberQueries, "useSubberProvidersQuery").mockReturnValue({
      data: [
        {
          provider_key: "opensubtitles_org",
          display_name: "OpenSubtitles.org",
          enabled: false,
          priority: 0,
          requires_account: true,
          has_credentials: false,
          available: true,
          availability_note: null,
        },
      ],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberProvidersQuery>);
    vi.spyOn(subberQueries, "usePutSubberProviderMutation").mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue({}),
      isPending: false,
    } as unknown as ReturnType<typeof subberQueries.usePutSubberProviderMutation>);
    vi.spyOn(subberQueries, "useSubberTestProviderMutation").mockReturnValue({
      mutateAsync: vi.fn().mockResolvedValue({ ok: true, message: "ok" }),
      isPending: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberTestProviderMutation>);
  });

  it("saves OpenSubtitles when Save is clicked", async () => {
    const putProvMutate = vi.fn().mockResolvedValue({});
    vi.spyOn(subberQueries, "usePutSubberProviderMutation").mockReturnValue({
      mutateAsync: putProvMutate,
      isPending: false,
    } as unknown as ReturnType<typeof subberQueries.usePutSubberProviderMutation>);

    const client = new QueryClient();
    render(wrap(<SubberProvidersTab canOperate />, client));
    await waitFor(() => expect(screen.getByTestId("subber-providers-tab")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /OpenSubtitles\.org/i }));
    await waitFor(() => expect(screen.getByTestId("subber-save-opensubtitles")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "u" } });
    fireEvent.click(screen.getByTestId("subber-save-opensubtitles"));
    await waitFor(() => expect(putProvMutate).toHaveBeenCalled());
  });

  it("renders subtitle providers section", async () => {
    const client = new QueryClient();
    render(wrap(<SubberProvidersTab canOperate />, client));
    await waitFor(() => expect(screen.getByTestId("subber-providers-section")).toBeInTheDocument());
  });

  it("runs test connection when Test is clicked", async () => {
    const testMut = vi.fn().mockResolvedValue({ ok: true, message: "Connected" });
    vi.spyOn(subberQueries, "useSubberTestOpensubtitlesMutation").mockReturnValue({
      mutateAsync: testMut,
      isPending: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberTestOpensubtitlesMutation>);
    const client = new QueryClient();
    render(wrap(<SubberProvidersTab canOperate />, client));
    await waitFor(() => expect(screen.getByTestId("subber-providers-tab")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /OpenSubtitles\.org/i }));
    await waitFor(() => expect(screen.getByTestId("subber-test-opensubtitles")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("subber-test-opensubtitles"));
    await waitFor(() => expect(testMut).toHaveBeenCalled());
  });

  it("shows unavailable providers as not available", async () => {
    vi.spyOn(subberQueries, "useSubberProvidersQuery").mockReturnValue({
      data: [
        {
          provider_key: "subscene",
          display_name: "Subscene",
          enabled: false,
          priority: 9,
          requires_account: false,
          has_credentials: false,
          available: false,
          availability_note: "Not available in this version.",
        },
      ],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof subberQueries.useSubberProvidersQuery>);
    const client = new QueryClient();
    render(wrap(<SubberProvidersTab canOperate />, client));
    await waitFor(() => expect(screen.getByText("Not available in this version.")).toBeInTheDocument());
  });
});
