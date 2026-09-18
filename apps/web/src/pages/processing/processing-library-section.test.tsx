/**
 * The Library tab (#505, reshaped by #568): its sub-navigation, the Files table's sorting, facet filtering and
 * selection, the "show files" links out of the breakdowns and Problems, and #505's final-removal confirmation.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import * as authQueries from "../../lib/auth/queries";
import * as libraryApi from "../../lib/processing/library-api";
import type {
  LibraryFile,
  LibraryFilesResult,
  LibraryOverview,
  LibraryProblemsResult,
  LibraryTotals,
} from "../../lib/processing/library-api";
import * as librariesApi from "../../lib/processing/libraries-api";
import type { ProcessingLibrary } from "../../lib/processing/libraries-api";
import { ProcessingLibrarySection } from "./processing-library-section";

function library(over: Partial<ProcessingLibrary> = {}): ProcessingLibrary {
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
  } as ProcessingLibrary;
}

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
}

function asOperator() {
  vi.spyOn(authQueries, "useMeQuery").mockReturnValue({
    data: { role: "operator" },
  } as ReturnType<typeof authQueries.useMeQuery>);
}

function totals(over: Partial<LibraryTotals> = {}): LibraryTotals {
  return {
    files: 2,
    size_bytes: 8_000_000,
    matches: 1,
    would_change: 1,
    cannot_process: 0,
    total_removed_audio_tracks: 1,
    total_removed_subtitle_tracks: 0,
    estimated_bytes_saved: 1_048_576,
    ...over,
  };
}

function file(over: Partial<LibraryFile> = {}): LibraryFile {
  return {
    path: "/srv/movies/library/film.mkv",
    size_bytes: 5_000_000,
    modified_at: 1_700_000_000,
    classification: "would_change",
    summary: "Would remove 1 audio track(s) (jpn).",
    reason: null,
    removed_audio_tracks: 1,
    removed_subtitle_tracks: 0,
    estimated_bytes_saved: 1_048_576,
    manager_kind: null,
    manager_title: null,
    video_codec: "hevc",
    video_height: 2160,
    resolution_class: "4k",
    audio_track_count: 2,
    subtitle_track_count: 1,
    audio_summary: "eng eac3 5.1, jpn aac stereo",
    subtitle_summary: "eng",
    link_count: null,
    problem_kind: null,
    ...over,
  };
}

function overview(over: Partial<LibraryOverview> = {}): LibraryOverview {
  return {
    library_id: 1,
    folders_configured: 1,
    scan: {
      job_id: 9,
      status: "completed",
      running: false,
      generated_at: 1_700_000_000,
      errors: [],
    },
    totals: totals(),
    breakdowns: {
      video_codec: [
        { value: "hevc", files: 1, size_bytes: 5_000_000, share: 0.5 },
        { value: "h264", files: 1, size_bytes: 3_000_000, share: 0.5 },
      ],
      resolution: [
        { value: "4k", files: 1, size_bytes: 5_000_000, share: 0.5 },
        { value: "1080p", files: 1, size_bytes: 3_000_000, share: 0.5 },
      ],
      audio: [{ value: "eac3 5.1", files: 2, size_bytes: 8_000_000, share: 1 }],
      audio_language: [
        { value: "eng", files: 2, size_bytes: 8_000_000, share: 1 },
        { value: "jpn", files: 1, size_bytes: 5_000_000, share: 0.5 },
      ],
      subtitle_language: [
        { value: "eng", files: 1, size_bytes: 5_000_000, share: 0.5 },
      ],
    },
    problems: [],
    ...over,
  };
}

function filesResult(
  over: Partial<LibraryFilesResult> = {},
): LibraryFilesResult {
  return {
    library_id: 1,
    scan: overview().scan,
    summary: totals(),
    filtered: totals(),
    files: [file()],
    total: 1,
    page: 1,
    page_size: 50,
    sort: "path",
    direction: "asc",
    ...over,
  };
}

function problemsResult(
  over: Partial<LibraryProblemsResult> = {},
): LibraryProblemsResult {
  return {
    library_id: 1,
    scan: overview().scan,
    groups: [],
    total: 0,
    ...over,
  };
}

/** Every query the Library tab makes, with sensible defaults a test can override. */
function mockLibrary(
  options: {
    overview?: LibraryOverview;
    files?: LibraryFilesResult;
    problems?: LibraryProblemsResult;
    folders?: string[];
  } = {},
) {
  vi.spyOn(librariesApi, "fetchProcessingLibraries").mockResolvedValue([
    library(),
  ]);
  vi.spyOn(libraryApi, "fetchLibrarySettings").mockResolvedValue({
    library_folders: options.folders ?? ["/srv/movies/library"],
    library_schedule_enabled: false,
    clean_hardlinked_files: false,
    skip_if_manager_would_redownload: true,
  });
  vi.spyOn(libraryApi, "fetchLibraryRedownloads").mockResolvedValue({
    library_id: 1,
    titles: [],
    total: 0,
  });
  const fetchOverview = vi
    .spyOn(libraryApi, "fetchLibraryOverview")
    .mockResolvedValue(options.overview ?? overview());
  const fetchFiles = vi
    .spyOn(libraryApi, "fetchLibraryFiles")
    .mockResolvedValue(options.files ?? filesResult());
  const fetchProblems = vi
    .spyOn(libraryApi, "fetchLibraryProblems")
    .mockResolvedValue(options.problems ?? problemsResult());
  return { fetchOverview, fetchFiles, fetchProblems };
}

async function openView(name: string) {
  fireEvent.click(await screen.findByRole("tab", { name }));
}

afterEach(() => {
  vi.restoreAllMocks();
});

it("opens on Overview with the library's totals and every breakdown", async () => {
  asOperator();
  mockLibrary();

  render(<ProcessingLibrarySection />, { wrapper });

  expect(await screen.findByTestId("library-view-tabs")).toBeInTheDocument();
  expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual([
    "Overview",
    "Files",
    "Codecs",
    "Languages",
    "Problems",
  ]);

  expect(await screen.findByTestId("library-figure-files")).toHaveTextContent(
    "2",
  );
  expect(screen.getByTestId("library-figure-would-change")).toHaveTextContent(
    "1",
  );
  expect(screen.getByTestId("library-scan-state").textContent).toContain(
    "Last scanned",
  );
  // The whole set of breakdowns is on Overview.
  expect(
    screen.getByTestId("library-breakdown-video_codec"),
  ).toBeInTheDocument();
  expect(
    screen.getByTestId("library-breakdown-subtitle_language"),
  ).toBeInTheDocument();
});

it("names a language the server canonicalised to its bibliographic code", async () => {
  asOperator();
  mockLibrary({
    overview: overview({
      breakdowns: {
        ...overview().breakdowns,
        // What OriginalLanguage.CanonicalLanguage produces for a track tagged "de", "deu" or "ger".
        audio_language: [{ value: "ger", files: 2, size_bytes: 200, share: 1 }],
      },
    }),
  });

  render(<ProcessingLibrarySection />, { wrapper });
  await openView("Languages");

  expect(await screen.findByText("German")).toBeInTheDocument();
  expect(screen.queryByText("ger")).not.toBeInTheDocument();
});

it("splits the breakdowns between the Codecs and Languages sub-views", async () => {
  asOperator();
  mockLibrary();

  render(<ProcessingLibrarySection />, { wrapper });
  await openView("Codecs");

  expect(
    await screen.findByTestId("library-breakdown-video_codec"),
  ).toBeInTheDocument();
  expect(
    screen.getByTestId("library-breakdown-resolution"),
  ).toBeInTheDocument();
  expect(screen.getByTestId("library-breakdown-audio")).toBeInTheDocument();
  expect(
    screen.queryByTestId("library-breakdown-audio_language"),
  ).not.toBeInTheDocument();

  await openView("Languages");

  expect(
    await screen.findByTestId("library-breakdown-audio_language"),
  ).toBeInTheDocument();
  expect(
    screen.getByTestId("library-breakdown-subtitle_language"),
  ).toBeInTheDocument();
  expect(
    screen.queryByTestId("library-breakdown-video_codec"),
  ).not.toBeInTheDocument();
});

it("sorts a breakdown table when its column header is clicked", async () => {
  asOperator();
  mockLibrary({
    overview: overview({
      breakdowns: {
        ...overview().breakdowns,
        video_codec: [
          { value: "hevc", files: 3, size_bytes: 300, share: 0.75 },
          { value: "av1", files: 1, size_bytes: 100, share: 0.25 },
        ],
      },
    }),
  });

  render(<ProcessingLibrarySection />, { wrapper });
  const table = await screen.findByTestId("library-breakdown-video_codec");
  const codecColumn = () =>
    within(table)
      .getAllByTestId("library-breakdown-row")
      .map((row) => within(row).getAllByRole("cell")[0].textContent);

  // Most files first by default.
  expect(codecColumn()).toEqual(["HEVC", "AV1"]);

  // By name: A to Z first, since that is what a name column is expected to do.
  fireEvent.click(within(table).getByRole("button", { name: /Codec/ }));
  expect(codecColumn()).toEqual(["AV1", "HEVC"]);

  // The same header again flips it.
  fireEvent.click(within(table).getByRole("button", { name: /Codec/ }));
  expect(codecColumn()).toEqual(["HEVC", "AV1"]);
});

it("a breakdown's Show files link opens Files filtered by that facet", async () => {
  asOperator();
  const { fetchFiles } = mockLibrary();

  render(<ProcessingLibrarySection />, { wrapper });
  await openView("Languages");
  const table = await screen.findByTestId("library-breakdown-audio_language");
  fireEvent.click(
    within(table).getAllByRole("button", { name: "Show files" })[1],
  );

  expect(
    await screen.findByTestId("library-files-section"),
  ).toBeInTheDocument();
  await waitFor(() =>
    expect(fetchFiles).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ facets: { audio_language: "jpn" }, page: 1 }),
    ),
  );
  expect(screen.getByTestId("library-files-active-filters")).toHaveTextContent(
    "Japanese",
  );
});

it("shows the media facts a file carries and re-fetches when a facet filter changes", async () => {
  asOperator();
  const { fetchFiles } = mockLibrary({
    files: filesResult({
      files: [
        file({ manager_kind: "radarr", manager_title: "Blade Runner 2049" }),
      ],
    }),
  });

  render(<ProcessingLibrarySection />, { wrapper });
  await openView("Files");

  expect(await screen.findByText("Blade Runner 2049")).toBeInTheDocument();
  expect(screen.getByText("HEVC · 4K")).toBeInTheDocument();
  expect(screen.getByText("eng eac3 5.1, jpn aac stereo")).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("Filter by resolution"), {
    target: { value: "4k" },
  });

  await waitFor(() =>
    expect(fetchFiles).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ facets: { resolution: "4k" } }),
    ),
  );
});

it("asks the server for a new sort when a Files column header is clicked", async () => {
  asOperator();
  const { fetchFiles } = mockLibrary();

  render(<ProcessingLibrarySection />, { wrapper });
  await openView("Files");
  fireEvent.click(await screen.findByRole("button", { name: /^Size/ }));

  await waitFor(() =>
    expect(fetchFiles).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ sort: "size", direction: "asc" }),
    ),
  );

  fireEvent.click(screen.getByRole("button", { name: /^Size/ }));

  await waitFor(() =>
    expect(fetchFiles).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ sort: "size", direction: "desc" }),
    ),
  );
});

it("selects every changeable file on the page at once", async () => {
  asOperator();
  mockLibrary({
    files: filesResult({
      files: [
        file({ path: "/srv/movies/library/a.mkv" }),
        file({ path: "/srv/movies/library/b.mkv" }),
        file({
          path: "/srv/movies/library/c.mkv",
          classification: "cannot_process",
        }),
      ],
      total: 3,
    }),
  });

  render(<ProcessingLibrarySection />, { wrapper });
  await openView("Files");

  fireEvent.click(
    await screen.findByLabelText("Select every changeable file on this page"),
  );

  // The unprocessable file is never selectable, so only the two changeable ones count.
  expect(screen.getByTestId("library-clean-button")).toHaveTextContent(
    "Clean selected (2)",
  );
  expect(
    screen.getByLabelText("Select /srv/movies/library/c.mkv"),
  ).toBeDisabled();
});

it("shows the exact final-removal confirmation text before cleaning, then cleans once confirmed", async () => {
  asOperator();
  mockLibrary();
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
      skipped_paths: [],
      warnings: [],
    });

  render(<ProcessingLibrarySection />, { wrapper });
  await openView("Files");

  fireEvent.click(
    await screen.findByLabelText("Select /srv/movies/library/film.mkv"),
  );
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

it("opens a file's expander with what the rules would do, from the #502 preview", async () => {
  asOperator();
  mockLibrary();
  const preview = vi
    .spyOn(
      await import("../../lib/processing/rules-preview-api"),
      "previewProcessingRules",
    )
    .mockResolvedValue({
      library_id: 1,
      media_scope: "movie",
      inspected_path: "/srv/movies/library/film.mkv",
      tracks: [
        {
          index: 1,
          type: "audio",
          codec: "eac3",
          language: "eng",
          title: "",
          channels: 6,
          action: "keep",
          default: true,
          forced: false,
          reasons: ["Primary language."],
        },
        {
          index: 2,
          type: "audio",
          codec: "aac",
          language: "jpn",
          title: "",
          channels: 2,
          action: "drop",
          default: false,
          forced: false,
          reasons: ["No language slot matches it."],
        },
      ],
      notes: [],
      metadata_notes: [],
      remux_required: true,
      estimated_size_reduction_bytes: 1_048_576,
      estimated_size_reduction_is_estimate: true,
      original_language: null,
    });

  render(<ProcessingLibrarySection />, { wrapper });
  await openView("Files");
  fireEvent.click(await screen.findByRole("button", { name: "Details" }));

  expect(await screen.findByTestId("library-file-preview")).toBeInTheDocument();
  expect(preview).toHaveBeenCalledWith({
    libraryId: 1,
    absolutePath: "/srv/movies/library/film.mkv",
  });
  expect(screen.getAllByTestId("library-file-preview-track")).toHaveLength(2);
  expect(screen.getByText("Remove")).toBeInTheDocument();
});

it("groups problems with what to do, and opens Files filtered to a group", async () => {
  asOperator();
  const { fetchFiles } = mockLibrary({
    problems: problemsResult({
      total: 2,
      groups: [
        {
          kind: "seeding",
          title: "Still shared with a download",
          what_to_do: "Wait until seeding finishes.",
          files: 2,
          size_bytes: 4_000_000,
          sample_paths: ["/srv/movies/library/seeding.mkv"],
        },
      ],
    }),
  });

  render(<ProcessingLibrarySection />, { wrapper });
  await openView("Problems");

  const group = await screen.findByTestId("library-problem-group");
  expect(group).toHaveTextContent("Still shared with a download");
  expect(group).toHaveTextContent("Wait until seeding finishes.");
  expect(group).toHaveTextContent("…and 1 more.");

  fireEvent.click(within(group).getByRole("button", { name: "Show files" }));

  await waitFor(() =>
    expect(fetchFiles).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ problem: "seeding" }),
    ),
  );
});

it("says nothing is in the way when a scanned library has no problems", async () => {
  asOperator();
  mockLibrary();

  render(<ProcessingLibrarySection />, { wrapper });
  await openView("Problems");

  expect(await screen.findByTestId("library-no-problems")).toBeInTheDocument();
});

it("explains what a scan does when nothing has been scanned yet", async () => {
  asOperator();
  mockLibrary({
    overview: overview({
      totals: totals({ files: 0, size_bytes: 0 }),
      scan: null,
    }),
    files: filesResult({ files: [], total: 0 }),
  });

  render(<ProcessingLibrarySection />, { wrapper });

  const empty = await screen.findByTestId("library-empty-state");
  expect(empty).toHaveTextContent("reads every file in this library's folders");
  expect(empty).toHaveTextContent("never writes to a file");
  expect(screen.getByTestId("library-scan-state")).toHaveTextContent(
    "This library has not been scanned yet.",
  );

  await openView("Files");
  expect(await screen.findByTestId("library-empty-state")).toBeInTheDocument();
});

it("shows a scan's own errors without hiding the rest of the view", async () => {
  asOperator();
  mockLibrary({
    overview: overview({
      scan: {
        job_id: 9,
        status: "completed",
        running: false,
        generated_at: 1_700_000_000,
        errors: ["Weir couldn't ask Radarr which titles it manages: timeout"],
      },
    }),
  });

  render(<ProcessingLibrarySection />, { wrapper });

  expect(await screen.findByTestId("library-scan-errors")).toHaveTextContent(
    "Weir couldn't ask Radarr",
  );
  expect(screen.getByTestId("library-figure-files")).toBeInTheDocument();
});

it("keeps the library folder settings reachable on Overview", async () => {
  asOperator();
  mockLibrary();

  render(<ProcessingLibrarySection />, { wrapper });

  expect(await screen.findByText("/srv/movies/library")).toBeInTheDocument();
  expect(screen.getByTestId("library-folders-section")).toBeInTheDocument();
});
