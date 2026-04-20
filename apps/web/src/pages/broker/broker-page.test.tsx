import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { UserPublic } from "../../lib/api/types";
import * as authQueries from "../../lib/auth/queries";
import * as brokerQueries from "../../lib/broker/broker-queries";
import * as suiteQueries from "../../lib/suite/queries";
import { AppShell } from "../../layouts/app-shell";
import {
  BROKER_TAB_CONNECTIONS_LABEL,
  BROKER_TAB_INDEXERS_LABEL,
  BROKER_TAB_JOBS_LABEL,
  BROKER_TAB_OVERVIEW_LABEL,
  BROKER_TAB_SEARCH_LABEL,
} from "./broker-display-names";
import { BrokerPage } from "./broker-page";

const operatorUser: UserPublic = { id: 1, username: "op", role: "operator" };

function wrap(ui: ReactNode, client: QueryClient) {
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/app/broker"]}>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

function emptyConnection(arrType: "sonarr" | "radarr") {
  return {
    id: arrType === "sonarr" ? 1 : 2,
    arr_type: arrType,
    url: "",
    api_key: "",
    sync_mode: "full",
    last_synced_at: null,
    last_sync_ok: null,
    last_sync_error: null,
    last_manual_sync_at: null,
    last_manual_sync_ok: null,
    indexer_fingerprint: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function idleMutation() {
  return {
    mutateAsync: vi.fn(),
    mutate: vi.fn(),
    isPending: false,
  } as unknown;
}

describe("BrokerPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    vi.spyOn(authQueries, "useMeQuery").mockReturnValue({
      data: operatorUser,
      isPending: false,
      isError: false,
    } as unknown as ReturnType<typeof authQueries.useMeQuery>);
    vi.spyOn(authQueries, "useLogoutMutation").mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof authQueries.useLogoutMutation>);
    vi.spyOn(suiteQueries, "useSuiteSettingsQuery").mockReturnValue({
      data: {
        product_display_name: "MediaMop",
        signed_in_home_notice: null,
        application_logs_enabled: true,
        app_timezone: "UTC",
        log_retention_days: 30,
        updated_at: "2026-01-01T00:00:00Z",
      },
      isPending: false,
      isError: false,
    } as unknown as ReturnType<typeof suiteQueries.useSuiteSettingsQuery>);

    vi.spyOn(brokerQueries, "useBrokerIndexersQuery").mockReturnValue({
      data: [],
      isPending: false,
      isError: false,
    } as unknown as ReturnType<typeof brokerQueries.useBrokerIndexersQuery>);
    vi.spyOn(brokerQueries, "useBrokerConnectionQuery").mockImplementation(
      (arrType: "sonarr" | "radarr") =>
        ({
          data: emptyConnection(arrType),
          isPending: false,
          isError: false,
        }) as unknown as ReturnType<typeof brokerQueries.useBrokerConnectionQuery>,
    );
    vi.spyOn(brokerQueries, "useBrokerSettingsQuery").mockReturnValue({
      data: { proxy_api_key: "test-proxy-key" },
      isPending: false,
      isError: false,
    } as unknown as ReturnType<typeof brokerQueries.useBrokerSettingsQuery>);
    vi.spyOn(brokerQueries, "useBrokerJobsQuery").mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof brokerQueries.useBrokerJobsQuery>);
    vi.spyOn(brokerQueries, "useBrokerSearchMutation").mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
      isError: false,
      isSuccess: false,
      data: undefined,
    } as unknown as ReturnType<typeof brokerQueries.useBrokerSearchMutation>);

    vi.spyOn(brokerQueries, "useUpdateBrokerConnectionMutation").mockReturnValue(
      idleMutation() as ReturnType<typeof brokerQueries.useUpdateBrokerConnectionMutation>,
    );
    vi.spyOn(brokerQueries, "useRotateBrokerProxyKeyMutation").mockReturnValue(
      idleMutation() as ReturnType<typeof brokerQueries.useRotateBrokerProxyKeyMutation>,
    );
    vi.spyOn(brokerQueries, "useBrokerManualSyncMutation").mockImplementation(
      () => idleMutation() as ReturnType<typeof brokerQueries.useBrokerManualSyncMutation>,
    );
    vi.spyOn(brokerQueries, "useUpdateBrokerIndexerMutation").mockReturnValue(
      idleMutation() as ReturnType<typeof brokerQueries.useUpdateBrokerIndexerMutation>,
    );
    vi.spyOn(brokerQueries, "useDeleteBrokerIndexerMutation").mockReturnValue(
      idleMutation() as ReturnType<typeof brokerQueries.useDeleteBrokerIndexerMutation>,
    );
    vi.spyOn(brokerQueries, "useTestBrokerIndexerMutation").mockReturnValue(
      idleMutation() as ReturnType<typeof brokerQueries.useTestBrokerIndexerMutation>,
    );
    vi.spyOn(brokerQueries, "useCreateBrokerIndexerMutation").mockReturnValue(
      idleMutation() as ReturnType<typeof brokerQueries.useCreateBrokerIndexerMutation>,
    );
  });

  it("renders data-testid broker-scope-page and all five tabs", async () => {
    const client = new QueryClient();
    render(wrap(<BrokerPage />, client));
    expect(screen.getByTestId("broker-scope-page")).toBeInTheDocument();
    const tabs = screen.getByTestId("broker-top-level-tabs");
    expect(within(tabs).getByRole("tab", { name: BROKER_TAB_OVERVIEW_LABEL })).toBeInTheDocument();
    expect(within(tabs).getByRole("tab", { name: BROKER_TAB_CONNECTIONS_LABEL })).toBeInTheDocument();
    expect(within(tabs).getByRole("tab", { name: BROKER_TAB_INDEXERS_LABEL })).toBeInTheDocument();
    expect(within(tabs).getByRole("tab", { name: BROKER_TAB_SEARCH_LABEL })).toBeInTheDocument();
    expect(within(tabs).getByRole("tab", { name: BROKER_TAB_JOBS_LABEL })).toBeInTheDocument();
  });

  it("switches between tabs", async () => {
    const client = new QueryClient();
    render(wrap(<BrokerPage />, client));
    await waitFor(() => expect(screen.getByTestId("broker-overview-tab")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("tab", { name: BROKER_TAB_JOBS_LABEL }));
    await waitFor(() => expect(screen.getByTestId("broker-jobs-tab")).toBeInTheDocument());
  });

  it("Connections tab shows Sonarr section above Radarr", async () => {
    const client = new QueryClient();
    render(wrap(<BrokerPage />, client));
    fireEvent.click(screen.getByRole("tab", { name: BROKER_TAB_CONNECTIONS_LABEL }));
    await waitFor(() => expect(screen.getByTestId("broker-connections-tab")).toBeInTheDocument());
    const son = screen.getByTestId("broker-connections-sonarr");
    const rad = screen.getByTestId("broker-connections-radarr");
    expect(son.compareDocumentPosition(rad) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("Indexers tab shows Torrent group above Usenet group", async () => {
    const client = new QueryClient();
    render(wrap(<BrokerPage />, client));
    fireEvent.click(screen.getByRole("tab", { name: BROKER_TAB_INDEXERS_LABEL }));
    await waitFor(() => expect(screen.getByTestId("broker-indexers-tab")).toBeInTheDocument());
    const torrent = screen.getByTestId("broker-indexers-torrent-group");
    const usenet = screen.getByTestId("broker-indexers-usenet-group");
    expect(torrent.compareDocumentPosition(usenet) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("Search tab renders query input and type selector", async () => {
    const client = new QueryClient();
    render(wrap(<BrokerPage />, client));
    fireEvent.click(screen.getByRole("tab", { name: BROKER_TAB_SEARCH_LABEL }));
    await waitFor(() => expect(screen.getByTestId("broker-search-tab")).toBeInTheDocument());
    expect(screen.getByPlaceholderText("Search titles…")).toBeInTheDocument();
    expect(screen.getByText("Type")).toBeInTheDocument();
  });

  it("Broker nav link appears above Fetcher in the sidebar", async () => {
    const client = new QueryClient();
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/app"]}>
          <Routes>
            <Route path="/app" element={<AppShell />}>
              <Route index element={<div />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByRole("link", { name: "Broker" })).toBeInTheDocument());
    const broker = screen.getByRole("link", { name: "Broker" });
    const fetcher = screen.getByRole("link", { name: "Fetcher" });
    expect(broker.compareDocumentPosition(fetcher) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
