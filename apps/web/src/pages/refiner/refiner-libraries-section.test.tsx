import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";

import * as api from "../../lib/refiner/libraries-api";
import type { RefinerLibrary } from "../../lib/refiner/libraries-api";
import * as authQueries from "../../lib/auth/queries";
import { RefinerLibrariesSection } from "./refiner-libraries-section";

function library(over: Partial<RefinerLibrary> = {}): RefinerLibrary {
  return {
    id: 1,
    name: "Movies",
    enabled: true,
    media_scope: "movie",
    display_order: 0,
    watched_folder: "/srv/movies/in",
    work_folder: "",
    output_folder: "/srv/movies/out",
    media_extensions_csv: ".mkv,.mp4",
    exclude_markers_csv: "__admin__",
    include_patterns_csv: "",
    exclude_patterns_csv: "",
    min_file_size_mb: 0,
    max_file_size_mb: 0,
    min_file_age_seconds: 60,
    exclude_hidden: true,
    top_level_only: false,
    scan_interval_seconds: 300,
    hold_minutes: 0,
    sidecar_patterns_csv: ".srt,.nfo",
    preserve_original_timestamps: false,
    file_detection_interval_seconds: 30,
    ignore_size_changes: false,
    skip_access_tests: false,
    file_system_events_enabled: true,
    schedule_grid: "",
    schedule_enabled: true,
    schedule_hours_limited: false,
    schedule_days: "",
    schedule_start: "00:00",
    schedule_end: "23:59",
    max_concurrent_files: 1,
    priority: 0,
    rule_set_id: null,
    manager_connection_ids: [],
    discovered_from_connection_id: null,
    discovered_library_key: null,
    active_job_count: 0,
    updated_at: null,
    ...over,
  };
}

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function asOperator() {
  vi.spyOn(authQueries, "useMeQuery").mockReturnValue({
    data: { role: "operator" },
  } as ReturnType<typeof authQueries.useMeQuery>);
}

afterEach(() => {
  vi.restoreAllMocks();
});

it("lists every library, not just Movies and TV", async () => {
  asOperator();
  vi.spyOn(api, "fetchRefinerLibraries").mockResolvedValue([
    library(),
    library({ id: 2, name: "TV", media_scope: "tv", display_order: 1 }),
    library({ id: 3, name: "Movies 4K", display_order: 2 }),
  ]);

  render(<RefinerLibrariesSection />, { wrapper });

  expect(await screen.findByText("Movies 4K")).toBeInTheDocument();
  expect(screen.getByText("TV")).toBeInTheDocument();
});

it("shows how much work is in flight, so a refusal makes sense", async () => {
  asOperator();
  vi.spyOn(api, "fetchRefinerLibraries").mockResolvedValue([
    library({ active_job_count: 3 }),
  ]);

  render(<RefinerLibrariesSection />, { wrapper });

  expect(await screen.findByText(/3 in progress/)).toBeInTheDocument();
});

it("surfaces the refusal reason when a library still has queued work", async () => {
  asOperator();
  vi.spyOn(api, "fetchRefinerLibraries").mockResolvedValue([library()]);
  vi.spyOn(api, "deleteRefinerLibrary").mockRejectedValue(
    new Error("Movies still has 2 jobs queued or running."),
  );

  render(<RefinerLibrariesSection />, { wrapper });
  fireEvent.click(await screen.findByTestId("refiner-library-remove-1"));

  await waitFor(() => {
    expect(screen.getByTestId("refiner-library-notice")).toHaveTextContent(
      /still has 2 jobs queued or running/,
    );
  });
});

it("adds a library through the API", async () => {
  asOperator();
  vi.spyOn(api, "fetchRefinerLibraries").mockResolvedValue([library()]);
  const create = vi
    .spyOn(api, "createRefinerLibrary")
    .mockResolvedValue(library({ id: 9, name: "Kids" }));

  render(<RefinerLibrariesSection />, { wrapper });
  fireEvent.click(await screen.findByTestId("refiner-library-add"));
  fireEvent.change(screen.getByPlaceholderText("Movies 4K"), {
    target: { value: "Kids" },
  });
  fireEvent.click(screen.getByTestId("refiner-library-save"));

  await waitFor(() => {
    expect(create).toHaveBeenCalledWith(
      expect.objectContaining({ name: "Kids", media_scope: "movie" }),
    );
  });
});

it("does not offer editing to a viewer", async () => {
  vi.spyOn(authQueries, "useMeQuery").mockReturnValue({
    data: { role: "viewer" },
  } as ReturnType<typeof authQueries.useMeQuery>);
  vi.spyOn(api, "fetchRefinerLibraries").mockResolvedValue([library()]);

  render(<RefinerLibrariesSection />, { wrapper });

  expect(await screen.findByText("Movies")).toBeInTheDocument();
  expect(screen.queryByTestId("refiner-library-add")).not.toBeInTheDocument();
});

it("says so plainly when nothing is configured yet", async () => {
  asOperator();
  vi.spyOn(api, "fetchRefinerLibraries").mockResolvedValue([]);

  render(<RefinerLibrariesSection />, { wrapper });

  expect(await screen.findByText(/No libraries yet/)).toBeInTheDocument();
});
