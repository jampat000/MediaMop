import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";

import * as authQueries from "../../lib/auth/queries";
import * as libraryApi from "../../lib/refiner/library-api";
import * as librariesApi from "../../lib/refiner/libraries-api";
import type { RefinerLibrary } from "../../lib/refiner/libraries-api";
import { RefinerLibrarySection } from "./refiner-library-section";

function library(over: Partial<RefinerLibrary> = {}): RefinerLibrary {
  return {
    id: 1,
    name: "Movies",
    enabled: true,
    media_type: "movie",
    display_order: 0,
    watched_folder: "/srv/movies/in",
    work_folder: "",
    output_folder: "/srv/movies/out",
    media_extensions_csv: ".mkv,.mp4",
    exclude_markers_csv: "",
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
    failure_policy: "pass_through",
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
    created_at: null,
    ...over,
  } as RefinerLibrary;
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

it("shows the library's folders and files, with a would-change file selectable", async () => {
  asOperator();
  vi.spyOn(librariesApi, "fetchRefinerLibraries").mockResolvedValue([
    library(),
  ]);
  vi.spyOn(libraryApi, "fetchLibrarySettings").mockResolvedValue({
    library_folders: ["/srv/movies/library"],
    library_schedule_enabled: false,
  });
  vi.spyOn(libraryApi, "fetchLibraryFiles").mockResolvedValue({
    library_id: 1,
    scan: { job_id: 9, status: "completed", generated_at: 1700000000 },
    summary: {
      matches: 1,
      would_change: 1,
      cannot_process: 0,
      total_removed_audio_tracks: 1,
      total_removed_subtitle_tracks: 0,
      estimated_bytes_saved: 1_048_576,
    },
    files: [
      {
        path: "/srv/movies/library/film.mkv",
        size_bytes: 5_000_000,
        classification: "would_change",
        summary: "Would remove 1 audio track(s) (jpn).",
        reason: null,
        removed_audio_tracks: 1,
        removed_subtitle_tracks: 0,
        estimated_bytes_saved: 1_048_576,
        manager_kind: null,
        manager_title: null,
      },
    ],
    total: 1,
  });

  render(<RefinerLibrarySection />, { wrapper });

  expect(await screen.findByText("/srv/movies/library")).toBeInTheDocument();
  expect(
    await screen.findByText("/srv/movies/library/film.mkv"),
  ).toBeInTheDocument();
  expect(screen.getByTestId("library-files-summary").textContent).toContain(
    "1 would change",
  );
});

it("shows the exact final-removal confirmation text before cleaning, then cleans once confirmed", async () => {
  asOperator();
  vi.spyOn(librariesApi, "fetchRefinerLibraries").mockResolvedValue([
    library(),
  ]);
  vi.spyOn(libraryApi, "fetchLibrarySettings").mockResolvedValue({
    library_folders: ["/srv/movies/library"],
    library_schedule_enabled: false,
  });
  vi.spyOn(libraryApi, "fetchLibraryFiles").mockResolvedValue({
    library_id: 1,
    scan: null,
    summary: {
      matches: 0,
      would_change: 1,
      cannot_process: 0,
      total_removed_audio_tracks: 1,
      total_removed_subtitle_tracks: 0,
      estimated_bytes_saved: 2_000_000,
    },
    files: [
      {
        path: "/srv/movies/library/film.mkv",
        size_bytes: 5_000_000,
        classification: "would_change",
        summary: "Would remove 1 audio track(s) (jpn).",
        reason: null,
        removed_audio_tracks: 1,
        removed_subtitle_tracks: 0,
        estimated_bytes_saved: 2_000_000,
        manager_kind: null,
        manager_title: null,
      },
    ],
    total: 1,
  });
  const clean = vi
    .spyOn(libraryApi, "cleanLibraryFiles")
    .mockResolvedValueOnce({
      kind: "confirmation_required",
      detail:
        "1 files, 1 tracks will be removed. Removed tracks are gone for good; getting one back means downloading the title again.",
      files_count: 1,
      tracks_count: 1,
      estimated_bytes_saved: 2_000_000,
    })
    .mockResolvedValueOnce({
      kind: "cleaned",
      queued: 1,
      job_ids: [42],
      files_count: 1,
      tracks_count: 1,
      estimated_bytes_saved: 2_000_000,
    });

  render(<RefinerLibrarySection />, { wrapper });

  const checkbox = await screen.findByLabelText(
    "Select /srv/movies/library/film.mkv",
  );
  fireEvent.click(checkbox);
  fireEvent.click(screen.getByTestId("library-clean-button"));

  await waitFor(() => expect(clean).toHaveBeenCalledTimes(1));
  expect(clean).toHaveBeenNthCalledWith(
    1,
    1,
    ["/srv/movies/library/film.mkv"],
    false,
  );

  // The exact #505 point 5 sentence, verbatim.
  expect(
    await screen.findByTestId("library-removal-confirmation-detail"),
  ).toHaveTextContent(
    "1 files, 1 tracks will be removed. Removed tracks are gone for good; getting one back means downloading the title again.",
  );

  fireEvent.click(screen.getByRole("button", { name: "Clean" }));
  await waitFor(() => expect(clean).toHaveBeenCalledTimes(2));
  expect(clean).toHaveBeenNthCalledWith(
    2,
    1,
    ["/srv/movies/library/film.mkv"],
    true,
  );
});
