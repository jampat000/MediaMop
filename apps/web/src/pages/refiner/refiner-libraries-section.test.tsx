import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";

import * as api from "../../lib/refiner/libraries-api";
import type { RefinerLibrary } from "../../lib/refiner/libraries-api";
import * as authQueries from "../../lib/auth/queries";
import * as managerApi from "../../lib/media-managers/media-managers-api";
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
    rejected_file_action: "leave",
    min_file_age_seconds: 60,
    created_after: null,
    created_before: null,
    modified_after: null,
    modified_before: null,
    exclude_hidden: true,
    top_level_only: false,
    scan_interval_seconds: 300,
    hold_minutes: 0,
    sidecar_patterns_csv: ".srt,.nfo",
    preserve_original_timestamps: false,
    output_collision_policy: "replace",
    hardware_decode_mode: "off",
    hardware_device: "",
    hardware_disabled_vendors_csv: "",
    ffmpeg_strictness: "normal",
    file_detection_interval_seconds: 30,
    ignore_size_changes: false,
    skip_access_tests: false,
    file_system_events_enabled: true,
    max_attempts: 3,
    retry_backoff_seconds: 300,
    retry_execution_failures: true,
    retry_preflight_failures: false,
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
    manager_coverage: "no_upstream_signal",
    manager_coverage_detail:
      "No media manager has been tested for this library.",
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
  vi.spyOn(managerApi, "fetchMediaManagerConnections").mockResolvedValue([]);
  vi.spyOn(api, "fetchRefinerRuleSets").mockResolvedValue([]);
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

it("discovers and imports selected manager libraries", async () => {
  asOperator();
  vi.mocked(managerApi.fetchMediaManagerConnections).mockResolvedValue([
    {
      id: 7,
      kind: "deluno",
      name: "Deluno",
      enabled: true,
      base_url: "http://deluno",
      api_key_is_saved: true,
      webhook_secret_is_set: false,
      webhook_url_path: "/hook",
      last_test_ok: true,
      last_test_at: null,
      last_test_detail: null,
      lanes: [],
    },
  ]);
  vi.spyOn(api, "fetchRefinerLibraries").mockResolvedValue([library()]);
  vi.spyOn(api, "discoverRefinerLibraries").mockResolvedValue([
    {
      key: "movies-4k",
      name: "Movies 4K",
      media_scope: "movie",
      root_path: "/manager/movies-4k",
      already_imported: false,
      local_path_problem: null,
      processes_before_import: true,
      output_path: "/manager/refined-4k",
      output_path_problem: null,
    },
  ]);
  const imported = vi
    .spyOn(api, "importDiscoveredRefinerLibraries")
    .mockResolvedValue([library({ id: 4, name: "Movies 4K" })]);

  render(<RefinerLibrariesSection />, { wrapper });
  fireEvent.change(await screen.findByLabelText("Media manager"), {
    target: { value: "7" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Discover libraries" }));
  fireEvent.click(await screen.findByLabelText(/Movies 4K/));
  fireEvent.click(screen.getByRole("button", { name: "Import selected" }));

  await waitFor(() => {
    expect(imported).toHaveBeenCalledWith(7, ["movies-4k"]);
    expect(screen.getByTestId("refiner-library-notice")).toHaveTextContent(
      /1 library was imported/,
    );
  });
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

it("saves the complete library contract without resetting hidden or advanced values", async () => {
  asOperator();
  const existing = library({
    include_patterns_csv: "*feature*",
    exclude_patterns_csv: "*sample*",
    max_file_size_mb: 80_000,
    rejected_file_action: "delete_file",
    created_after: "2026-01-01T00:00:00Z",
    created_before: "2027-01-01T00:00:00Z",
    modified_after: "2026-02-01T00:00:00Z",
    modified_before: "2026-12-01T00:00:00Z",
    sidecar_patterns_csv: ".srt,.nfo,.jpg",
    preserve_original_timestamps: true,
    output_collision_policy: "keep_both",
    hardware_decode_mode: "device",
    hardware_device: "qsv",
    hardware_disabled_vendors_csv: "nvidia",
    ffmpeg_strictness: "strict",
    max_attempts: 7,
    retry_backoff_seconds: 120,
    retry_execution_failures: false,
    retry_preflight_failures: true,
    schedule_enabled: false,
    schedule_hours_limited: true,
    schedule_days: "mon,tue",
    schedule_start: "01:00",
    schedule_end: "06:00",
    priority: 12,
  });
  vi.spyOn(api, "fetchRefinerLibraries").mockResolvedValue([existing]);
  const update = vi
    .spyOn(api, "updateRefinerLibrary")
    .mockResolvedValue(existing);

  render(<RefinerLibrariesSection />, { wrapper });
  fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
  fireEvent.click(screen.getByTestId("refiner-library-save"));

  await waitFor(() => {
    expect(update).toHaveBeenCalledWith(
      1,
      expect.objectContaining({
        include_patterns_csv: "*feature*",
        exclude_patterns_csv: "*sample*",
        max_file_size_mb: 80_000,
        rejected_file_action: "delete_file",
        created_after: "2026-01-01T00:00:00.000Z",
        created_before: "2027-01-01T00:00:00.000Z",
        modified_after: "2026-02-01T00:00:00.000Z",
        modified_before: "2026-12-01T00:00:00.000Z",
        sidecar_patterns_csv: ".srt,.nfo,.jpg",
        preserve_original_timestamps: true,
        output_collision_policy: "keep_both",
        hardware_decode_mode: "device",
        hardware_device: "qsv",
        hardware_disabled_vendors_csv: "nvidia",
        ffmpeg_strictness: "strict",
        max_attempts: 7,
        retry_backoff_seconds: 120,
        retry_execution_failures: false,
        retry_preflight_failures: true,
        schedule_enabled: false,
        schedule_hours_limited: true,
        schedule_days: "mon,tue",
        schedule_start: "01:00",
        schedule_end: "06:00",
        priority: 12,
      }),
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
