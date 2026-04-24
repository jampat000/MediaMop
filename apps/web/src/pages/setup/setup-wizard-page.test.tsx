import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { qk } from "../../lib/auth/queries";
import { suiteSettingsQueryKey } from "../../lib/suite/queries";
import { SetupWizardPage } from "./setup-wizard-page";

const {
  navigateMock,
  suiteMutateAsyncMock,
  refinerMutateAsyncMock,
  subberMutateAsyncMock,
  patchPrunerInstanceMock,
  postPrunerInstanceMock,
  refinerQueryData,
  subberQueryData,
  prunerQueryData,
} = vi.hoisted(() => ({
  navigateMock: vi.fn(),
  suiteMutateAsyncMock: vi.fn(),
  refinerMutateAsyncMock: vi.fn(),
  subberMutateAsyncMock: vi.fn(),
  patchPrunerInstanceMock: vi.fn(),
  postPrunerInstanceMock: vi.fn(),
  refinerQueryData: {
    refiner_watched_folder: "",
    refiner_work_folder: null,
    refiner_output_folder: "",
    refiner_tv_watched_folder: "",
    refiner_tv_work_folder: null,
    refiner_tv_output_folder: "",
    movie_watched_folder_check_interval_seconds: 300,
    tv_watched_folder_check_interval_seconds: 300,
  },
  subberQueryData: {
    sonarr_base_url: "",
    radarr_base_url: "",
    language_preferences: ["en"],
  },
  prunerQueryData: [],
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

vi.mock("../../lib/suite/queries", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/suite/queries")>();
  return {
    ...actual,
    useSuiteSettingsSaveMutation: () => ({
      isPending: false,
      mutateAsync: suiteMutateAsyncMock,
    }),
  };
});

vi.mock("../../lib/refiner/queries", () => ({
  useRefinerPathSettingsQuery: () => ({
    isPending: false,
    data: refinerQueryData,
  }),
  useRefinerPathSettingsSaveMutation: () => ({
    isPending: false,
    mutateAsync: refinerMutateAsyncMock,
  }),
}));

vi.mock("../../lib/subber/subber-queries", () => ({
  useSubberSettingsQuery: () => ({
    isPending: false,
    data: subberQueryData,
  }),
  usePutSubberSettingsMutation: () => ({
    isPending: false,
    mutateAsync: subberMutateAsyncMock,
  }),
}));

vi.mock("../../lib/pruner/queries", () => ({
  usePrunerInstancesQuery: () => ({
    isPending: false,
    data: prunerQueryData,
  }),
}));

vi.mock("../../lib/pruner/api", () => ({
  postPrunerInstance: postPrunerInstanceMock,
  patchPrunerInstance: patchPrunerInstanceMock,
}));

vi.mock("../../lib/api/auth-api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api/auth-api")>();
  return {
    ...actual,
    fetchCsrfToken: vi.fn().mockResolvedValue("csrf-token"),
  };
});

function wrap(ui: ReactNode, client: QueryClient) {
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

function renderWizard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  client.setQueryData(qk.me, { id: 1, username: "admin", role: "admin" });
  client.setQueryData(suiteSettingsQueryKey, {
    product_display_name: "MediaMop",
    signed_in_home_notice: null,
    setup_wizard_state: "pending",
    app_timezone: "UTC",
    log_retention_days: 30,
    configuration_backup_enabled: false,
    configuration_backup_interval_hours: 24,
    configuration_backup_preferred_time: "02:00",
    configuration_backup_last_run_at: null,
    updated_at: "2026-04-23T00:00:00Z",
  });
  return render(wrap(<SetupWizardPage />, client));
}

describe("SetupWizardPage", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    suiteMutateAsyncMock.mockReset();
    refinerMutateAsyncMock.mockReset();
    subberMutateAsyncMock.mockReset();
    postPrunerInstanceMock.mockReset();
    patchPrunerInstanceMock.mockReset();
    suiteMutateAsyncMock.mockResolvedValue({});
    refinerMutateAsyncMock.mockResolvedValue({});
    subberMutateAsyncMock.mockResolvedValue({});
    postPrunerInstanceMock.mockResolvedValue({});
    patchPrunerInstanceMock.mockResolvedValue({});
  });

  it("skips and persists skipped wizard state", async () => {
    renderWizard();

    fireEvent.click(screen.getByTestId("setup-wizard-skip"));

    await waitFor(() => {
      expect(suiteMutateAsyncMock).toHaveBeenCalledWith(
        expect.objectContaining({
          setup_wizard_state: "skipped",
          app_timezone: "UTC",
          configuration_backup_preferred_time: "02:00",
        }),
      );
    });
  });

  it("completes and saves backup plus module starter settings", async () => {
    renderWizard();

    fireEvent.change(screen.getByDisplayValue("02:00"), { target: { value: "03:30" } });
    fireEvent.change(screen.getByPlaceholderText("Movies watched folder"), { target: { value: "D:\\Movies" } });
    fireEvent.change(screen.getByPlaceholderText("Movies output folder"), { target: { value: "E:\\MoviesOut" } });
    fireEvent.change(screen.getByPlaceholderText("http://127.0.0.1:8989"), { target: { value: "http://sonarr:8989" } });
    fireEvent.change(screen.getByPlaceholderText("Sonarr API key"), { target: { value: "sonarr-key" } });
    fireEvent.change(screen.getByPlaceholderText("http://127.0.0.1:8096"), { target: { value: "http://jf:8096" } });
    fireEvent.change(screen.getByPlaceholderText("API key"), { target: { value: "jf-key" } });
    fireEvent.click(screen.getByText("Refiner"));
    fireEvent.click(screen.getByRole("button", { name: "Finish setup" }));

    await waitFor(() => {
      expect(suiteMutateAsyncMock).toHaveBeenCalledWith(
        expect.objectContaining({
          setup_wizard_state: "completed",
          configuration_backup_preferred_time: "03:30",
        }),
      );
    });
    expect(refinerMutateAsyncMock).toHaveBeenCalledWith(
      expect.objectContaining({
        refiner_watched_folder: "D:\\Movies",
        refiner_output_folder: "E:\\MoviesOut",
      }),
    );
    expect(subberMutateAsyncMock).toHaveBeenCalledWith(
      expect.objectContaining({
        sonarr_base_url: "http://sonarr:8989",
        sonarr_api_key: "sonarr-key",
        language_preferences: ["en"],
      }),
    );
    expect(postPrunerInstanceMock).toHaveBeenCalledWith(
      expect.objectContaining({
        provider: "jellyfin",
        base_url: "http://jf:8096",
        credentials: { api_key: "jf-key" },
      }),
    );
    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith("/app/refiner", { replace: true });
    });
  });
});
