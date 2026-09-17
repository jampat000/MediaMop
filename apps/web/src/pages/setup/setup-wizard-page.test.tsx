import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { qk } from "../../lib/auth/queries";
import type { RefinerLibrary } from "../../lib/refiner/libraries-api";
import { suiteSettingsQueryKey } from "../../lib/suite/queries";
import { SetupWizardPage } from "./setup-wizard-page";

const {
  navigateMock,
  suiteMutateAsyncMock,
  createLibraryMock,
  updateLibraryMock,
  librariesState,
} = vi.hoisted(() => ({
  navigateMock: vi.fn(),
  suiteMutateAsyncMock: vi.fn(),
  createLibraryMock: vi.fn(),
  updateLibraryMock: vi.fn(),
  librariesState: { data: [] as RefinerLibrary[] },
}));

function existingLibrary(over: Partial<RefinerLibrary>): RefinerLibrary {
  return {
    id: 7,
    name: "Films",
    enabled: true,
    media_type: "movie",
    display_order: 0,
    watched_folder: "C:\\Old\\Movies",
    work_folder: "C:\\Work",
    output_folder: "C:\\Old\\MoviesOut",
    scan_interval_seconds: 900,
    rule_set_id: 3,
    manager_connection_ids: [2],
    ...over,
  } as RefinerLibrary;
}

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

vi.mock("../../lib/suite/queries", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../lib/suite/queries")>();
  return {
    ...actual,
    useSuiteSettingsSaveMutation: () => ({
      isPending: false,
      mutateAsync: suiteMutateAsyncMock,
    }),
  };
});

vi.mock("../../lib/refiner/libraries-queries", () => ({
  useRefinerLibrariesQuery: () => ({
    isPending: false,
    data: librariesState.data,
  }),
  useCreateRefinerLibrary: () => ({
    isPending: false,
    mutateAsync: createLibraryMock,
  }),
  useUpdateRefinerLibrary: () => ({
    isPending: false,
    mutateAsync: updateLibraryMock,
  }),
}));

vi.mock("../../lib/api/auth-api", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../lib/api/auth-api")>();
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
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
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
    createLibraryMock.mockReset();
    updateLibraryMock.mockReset();
    librariesState.data = [];
    suiteMutateAsyncMock.mockResolvedValue({});
    createLibraryMock.mockResolvedValue({});
    updateLibraryMock.mockResolvedValue({});
  });

  it("offers In hand as the start page at / and the dashboard at /dashboard", async () => {
    renderWizard();

    fireEvent.click(screen.getByText("Dashboard"));
    fireEvent.click(screen.getByRole("button", { name: "Finish setup" }));

    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith("/dashboard", {
        replace: true,
      });
    });
    expect(screen.getByText("In hand")).toBeInTheDocument();
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

    fireEvent.change(screen.getByDisplayValue("02:00"), {
      target: { value: "03:30" },
    });
    fireEvent.change(screen.getByPlaceholderText("Movies watched folder"), {
      target: { value: "D:\\Movies" },
    });
    fireEvent.change(screen.getByPlaceholderText("Movies output folder"), {
      target: { value: "E:\\MoviesOut" },
    });
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
    expect(createLibraryMock).toHaveBeenCalledTimes(1);
    expect(createLibraryMock).toHaveBeenCalledWith({
      name: "Movies",
      media_type: "movie",
      watched_folder: "D:\\Movies",
      output_folder: "E:\\MoviesOut",
    });
    expect(updateLibraryMock).not.toHaveBeenCalled();
    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith("/refiner", {
        replace: true,
      });
    });
  });

  it("creates a library for each media type that has folders and none yet", async () => {
    renderWizard();

    fireEvent.change(screen.getByPlaceholderText("TV watched folder"), {
      target: { value: "D:\\TV" },
    });
    fireEvent.change(screen.getByPlaceholderText("TV output folder"), {
      target: { value: "E:\\TVOut" },
    });
    fireEvent.change(screen.getByPlaceholderText("Movies watched folder"), {
      target: { value: "D:\\Movies" },
    });
    fireEvent.change(screen.getByPlaceholderText("Movies output folder"), {
      target: { value: "E:\\MoviesOut" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Finish setup" }));

    await waitFor(() => {
      expect(createLibraryMock).toHaveBeenCalledTimes(2);
    });
    expect(createLibraryMock).toHaveBeenCalledWith(
      expect.objectContaining({ name: "TV", media_type: "tv" }),
    );
    expect(createLibraryMock).toHaveBeenCalledWith(
      expect.objectContaining({ name: "Movies", media_type: "movie" }),
    );
    expect(updateLibraryMock).not.toHaveBeenCalled();
  });

  it("updates the first existing library of a media type instead of adding another", async () => {
    librariesState.data = [
      existingLibrary({ id: 9, name: "4K films", display_order: 1 }),
      existingLibrary({ id: 7, name: "Films", display_order: 0 }),
    ];
    renderWizard();

    const watched = screen.getByPlaceholderText("Movies watched folder");
    expect(watched).toHaveValue("C:\\Old\\Movies");
    fireEvent.change(watched, { target: { value: "D:\\Movies" } });
    fireEvent.click(screen.getByRole("button", { name: "Finish setup" }));

    await waitFor(() => {
      expect(updateLibraryMock).toHaveBeenCalledTimes(1);
    });
    expect(updateLibraryMock).toHaveBeenCalledWith({
      id: 7,
      data: expect.objectContaining({
        name: "Films",
        media_type: "movie",
        watched_folder: "D:\\Movies",
        output_folder: "C:\\Old\\MoviesOut",
        work_folder: "C:\\Work",
        scan_interval_seconds: 900,
        rule_set_id: 3,
        manager_connection_ids: [2],
      }),
    });
    expect(createLibraryMock).not.toHaveBeenCalled();
  });
});
