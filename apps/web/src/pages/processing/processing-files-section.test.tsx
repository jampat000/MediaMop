import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";

import * as api from "../../lib/processing/files-api";
import * as remuxApi from "../../lib/processing/file-remux-pass-api";
import type {
  ProcessingFile,
  ProcessingFilesPage,
} from "../../lib/processing/files-api";
import * as librariesApi from "../../lib/processing/libraries-api";
import * as authQueries from "../../lib/auth/queries";
import * as pauseApi from "../../lib/pause/pause-api";
import { ProcessingFilesSection } from "./processing-files-section";

function file(over: Partial<ProcessingFile> = {}): ProcessingFile {
  return {
    id: 1,
    library_id: 1,
    library_name: "Movies",
    relative_path: "Some Film/film.mkv",
    status: "unprocessed",
    status_reason: "Ready to process as part of Movies.",
    blocked_by_connection: null,
    size_bytes: 2048,
    failure_class: null,
    failure_attempts: 0,
    next_retry_at: null,
    output_collision_policy: null,
    output_collision_action: null,
    output_collision_reason: null,
    video_width: null,
    video_height: null,
    video_codec: null,
    audio_track_count: null,
    subtitle_track_count: null,
    duration_seconds: null,
    direct_play: [],
    progress_percent: null,
    progress_message: null,
    progress_eta_seconds: null,
    hold_until: null,
    size_changed_at: null,
    created_at: "2026-09-01T08:00:00Z",
    updated_at: "2026-09-01T08:05:00Z",
    last_seen_at: null,
    last_attempt_at: null,
    ...over,
  };
}

function page(over: Partial<ProcessingFilesPage> = {}): ProcessingFilesPage {
  return {
    files: [file()],
    status_counts: { unprocessed: 1, on_hold: 0, blocked_upstream: 0 },
    returned: 1,
    limit: 200,
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
  vi.spyOn(librariesApi, "fetchProcessingLibraries").mockResolvedValue([]);
  vi.spyOn(pauseApi, "fetchPause").mockResolvedValue({
    paused: false,
    paused_until: null,
    scan_while_paused: true,
    reason: "Processing is running.",
    in_flight_policy: "Work already running finishes.",
  });
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

it("shows the reason a file is not being processed", async () => {
  asOperator();
  vi.spyOn(api, "fetchProcessingFiles").mockResolvedValue(
    page({
      files: [
        file({
          status: "blocked_upstream",
          status_reason:
            "Deluno (Main) is still importing this file, so Weir left it alone for now.",
          blocked_by_connection: "Deluno (Main)",
        }),
      ],
      status_counts: { blocked_upstream: 1 },
    }),
  );

  render(<ProcessingFilesSection />, { wrapper });

  expect(
    await screen.findByText(/Deluno \(Main\) is still importing this file/),
  ).toBeInTheDocument();
});

it("shows first-seen, last-check, and processing-attempt timestamps on every file", async () => {
  asOperator();
  vi.spyOn(api, "fetchProcessingFiles").mockResolvedValue(
    page({
      files: [
        file({
          created_at: "2026-09-01T08:00:00Z",
          last_seen_at: "2026-09-01T08:05:00Z",
          last_attempt_at: "2026-09-01T08:04:00Z",
        }),
      ],
    }),
  );

  render(<ProcessingFilesSection />, { wrapper });

  const timeline = await screen.findByTestId("processing-file-timestamps-1");
  expect(timeline).toHaveTextContent("First seen");
  expect(timeline).toHaveTextContent("Last checked");
  expect(timeline).toHaveTextContent("Last processing attempt");
  expect(timeline).not.toHaveTextContent("Not recorded");
});

it("treats timezone-less backend timestamps as UTC in relative ages", async () => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-09-01T02:04:00Z"));
  asOperator();
  vi.spyOn(api, "fetchProcessingFiles").mockResolvedValue(
    page({
      files: [
        file({
          created_at: "2026-09-01T01:19:00",
          last_seen_at: "2026-09-01T02:04:00",
          last_attempt_at: "2026-09-01T01:20:00",
        }),
      ],
    }),
  );

  render(<ProcessingFilesSection />, { wrapper });

  const timeline = await screen.findByTestId("processing-file-timestamps-1");
  expect(timeline).toHaveTextContent("45 min ago");
  expect(timeline).toHaveTextContent("just now");
  expect(timeline).toHaveTextContent("44 min ago");
  expect(timeline).not.toHaveTextContent("10 hr ago");
});

it("shows a bucket for every state, including empty ones", async () => {
  asOperator();
  vi.spyOn(api, "fetchProcessingFiles").mockResolvedValue(page());

  render(<ProcessingFilesSection />, { wrapper });

  // The lead band draws one segment per state, an empty one included: it carries the
  // state's name and its count, and it is a real button that filters the list.
  const onHold = await screen.findByTestId("processing-files-bucket-on_hold");
  expect(onHold).toHaveTextContent("On hold");
  expect(onHold).toHaveTextContent("0");
  expect(onHold.tagName).toBe("BUTTON");
  expect(
    screen.getByTestId("processing-files-bucket-out_of_schedule"),
  ).toBeInTheDocument();
  expect(
    screen.getByTestId("processing-files-bucket-disabled"),
  ).toBeInTheDocument();
});

it("labels paused work as paused instead of claiming its schedule is closed", async () => {
  asOperator();
  vi.mocked(pauseApi.fetchPause).mockResolvedValue({
    paused: true,
    paused_until: null,
    scan_while_paused: true,
    reason: "Processing is paused until it is resumed.",
    in_flight_policy: "Work already running finishes.",
  });
  vi.spyOn(api, "fetchProcessingFiles").mockResolvedValue(
    page({
      files: [
        file({
          status: "out_of_schedule",
          status_reason:
            "Processing is paused. Weir will start work again when you resume it.",
        }),
      ],
      status_counts: { out_of_schedule: 1 },
    }),
  );

  render(<ProcessingFilesSection />, { wrapper });

  // Both the row's status pill and the band segment for that state read "Paused" — the
  // point of the guard is that neither of them claims the schedule is closed.
  expect(await screen.findAllByText("Paused")).toHaveLength(2);
  expect(screen.getByText("Processing is paused.")).toBeInTheDocument();
  expect(screen.getByText(/Use Resume at the top/)).toBeInTheDocument();
  expect(
    screen.queryByText("This library is outside its schedule."),
  ).not.toBeInTheDocument();
});

it("asks for a re-check when a saved pause reason is stale", async () => {
  asOperator();
  vi.spyOn(api, "fetchProcessingFiles").mockResolvedValue(
    page({
      files: [
        file({
          status: "out_of_schedule",
          status_reason:
            "Processing is paused. Weir will start work again when you resume it.",
        }),
      ],
      status_counts: { out_of_schedule: 1 },
    }),
  );

  render(<ProcessingFilesSection />, { wrapper });

  expect(await screen.findAllByText(/Needs re-check/)).toHaveLength(2);
  expect(screen.getByText("Refresh this file's status.")).toBeInTheDocument();
  expect(screen.getByText(/Use Check again/)).toBeInTheDocument();
  expect(screen.queryByText("Processing is paused.")).not.toBeInTheDocument();
  // A file whose pause reason has gone stale still counts as needing action. That total
  // used to sit in a tile above the bucket row; it now reads out in the band's caption.
  expect(screen.getByTestId("processing-files-flow-caption")).toHaveTextContent(
    "1 file needs action.",
  );
});

it("filters by bucket", async () => {
  asOperator();
  const fetchFiles = vi
    .spyOn(api, "fetchProcessingFiles")
    .mockResolvedValue(page());

  render(<ProcessingFilesSection />, { wrapper });
  fireEvent.click(await screen.findByTestId("processing-files-bucket-on_hold"));

  await waitFor(() => {
    expect(fetchFiles).toHaveBeenCalledWith(
      expect.objectContaining({ file_status: "on_hold" }),
    );
  });
});

it("says removing a file only removes the record", async () => {
  asOperator();
  vi.spyOn(api, "fetchProcessingFiles").mockResolvedValue(page());

  render(<ProcessingFilesSection />, { wrapper });

  const button = await screen.findByTestId("processing-file-forget-1");
  expect(button).toHaveAttribute(
    "title",
    expect.stringContaining("file on disk is untouched"),
  );
});

it("does not offer removal to a viewer", async () => {
  vi.spyOn(authQueries, "useMeQuery").mockReturnValue({
    data: { role: "viewer" },
  } as ReturnType<typeof authQueries.useMeQuery>);
  vi.spyOn(librariesApi, "fetchProcessingLibraries").mockResolvedValue([]);
  vi.spyOn(api, "fetchProcessingFiles").mockResolvedValue(page());

  render(<ProcessingFilesSection />, { wrapper });

  expect(await screen.findByText("Some Film/film.mkv")).toBeInTheDocument();
  expect(
    screen.queryByTestId("processing-file-forget-1"),
  ).not.toBeInTheDocument();
});

it("explains an empty list rather than showing nothing", async () => {
  asOperator();
  vi.spyOn(api, "fetchProcessingFiles").mockResolvedValue(
    page({ files: [], status_counts: {}, returned: 0 }),
  );

  render(<ProcessingFilesSection />, { wrapper });

  expect(await screen.findByText(/No files match/)).toBeInTheDocument();
});

it("shows a held file's release time so the wait is not open-ended", async () => {
  asOperator();
  vi.spyOn(api, "fetchProcessingFiles").mockResolvedValue(
    page({
      files: [
        file({
          status: "on_hold",
          status_reason:
            "This file is still growing, so something is writing to it.",
          hold_until: new Date(Date.now() + 30_000).toISOString(),
        }),
      ],
    }),
  );

  render(<ProcessingFilesSection />, { wrapper });

  expect(
    await screen.findByTestId("processing-file-hold-until-1"),
  ).toHaveTextContent(/Ready in about 30s/);
});

it("invents no release time when the wait is on a writer rather than the clock", async () => {
  asOperator();
  vi.spyOn(api, "fetchProcessingFiles").mockResolvedValue(
    page({
      files: [
        file({
          status: "on_hold",
          status_reason: "Weir could not open this file for reading.",
          hold_until: null,
        }),
      ],
    }),
  );

  render(<ProcessingFilesSection />, { wrapper });

  expect(
    await screen.findByText(/could not open this file for reading/),
  ).toBeInTheDocument();
  expect(
    screen.queryByTestId("processing-file-hold-until-1"),
  ).not.toBeInTheDocument();
});

it("offers move to top only for work that has not started", async () => {
  asOperator();
  vi.spyOn(api, "fetchProcessingFiles").mockResolvedValue(
    page({
      files: [
        file({ id: 1, status: "unprocessed" }),
        file({ id: 2, status: "processing", relative_path: "Other/other.mkv" }),
      ],
    }),
  );

  render(<ProcessingFilesSection />, { wrapper });

  expect(
    await screen.findByTestId("processing-file-move-to-top-1"),
  ).toBeInTheDocument();
  // A running file cannot be started earlier; a button here would be a lie.
  expect(
    screen.queryByTestId("processing-file-move-to-top-2"),
  ).not.toBeInTheDocument();
});

it("shows the server's own words about whether the move happened", async () => {
  asOperator();
  vi.spyOn(api, "fetchProcessingFiles").mockResolvedValue(
    page({ files: [file({ id: 1, status: "unprocessed" })] }),
  );
  vi.spyOn(api, "moveProcessingFileToTop").mockResolvedValue({
    moved: false,
    detail: "There is no queued work for this file to move.",
  });

  render(<ProcessingFilesSection />, { wrapper });
  fireEvent.click(await screen.findByTestId("processing-file-move-to-top-1"));

  expect(
    await screen.findByTestId("processing-files-notice"),
  ).toHaveTextContent("There is no queued work for this file to move.");
});

it("offers a retry on a failed file and shows what the server said", async () => {
  asOperator();
  vi.spyOn(api, "fetchProcessingFiles").mockResolvedValue(
    page({
      files: [
        file({
          id: 1,
          status: "processing_failed",
          failure_class: "execution",
          failure_attempts: 3,
        }),
      ],
    }),
  );
  vi.spyOn(api, "requeueProcessingFile").mockResolvedValue({
    requeued: 1,
    skipped: 0,
    detail:
      "Queued again by hand. It starts as soon as there is capacity for it.",
  });

  render(<ProcessingFilesSection />, { wrapper });
  fireEvent.click(await screen.findByTestId("processing-file-requeue-1"));

  expect(
    await screen.findByTestId("processing-files-notice"),
  ).toHaveTextContent(/Queued again by hand/);
});

it("passes an edge-case file through unchanged only after explaining source cleanup", async () => {
  asOperator();
  vi.spyOn(api, "fetchProcessingFiles").mockResolvedValue(
    page({
      files: [file({ id: 1, status: "processing_failed" })],
      status_counts: { processing_failed: 1 },
    }),
  );
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
  const enqueue = vi
    .spyOn(remuxApi, "postProcessingFileRemuxPassEnqueue")
    .mockResolvedValue({
      ok: true,
      job_id: 44,
      dedupe_key: "pass-through-44",
      job_kind: "processing.file.remux_pass.v1",
    });

  render(<ProcessingFilesSection />, { wrapper });
  fireEvent.click(await screen.findByTestId("processing-file-pass-through-1"));

  expect(confirm).toHaveBeenCalledWith(
    expect.stringMatching(
      /copy and validate.*output folder.*remove the watched source/s,
    ),
  );
  await waitFor(() => {
    expect(enqueue).toHaveBeenCalledWith(
      expect.objectContaining({
        relative_media_path: "Some Film/film.mkv",
        pass_through_unchanged: true,
      }),
    );
  });
  expect(
    await screen.findByTestId("processing-files-notice"),
  ).toHaveTextContent(/Queued to pass through unchanged/);
});

it("does not offer a retry on a file that has not failed", async () => {
  asOperator();
  vi.spyOn(api, "fetchProcessingFiles").mockResolvedValue(
    page({ files: [file({ id: 1, status: "unprocessed" })] }),
  );

  render(<ProcessingFilesSection />, { wrapper });

  await screen.findByText("Some Film/film.mkv");
  expect(
    screen.queryByTestId("processing-file-requeue-1"),
  ).not.toBeInTheDocument();
});

it("asks the managers why a file is held and shows their own words", async () => {
  asOperator();
  vi.spyOn(api, "fetchProcessingFiles").mockResolvedValue(
    page({ files: [file({ id: 1, status: "blocked_upstream" })] }),
  );
  vi.spyOn(api, "fetchProcessingWhyHeld").mockResolvedValue({
    file_id: 1,
    relative_path: "Some Film/film.mkv",
    library_name: "Movies",
    recorded_status: "blocked_upstream",
    recorded_reason: "Deluno (Main) is still importing this file.",
    verdict: "wait_upstream",
    owned: true,
    blocked_upstream: true,
    blocked_by_connection: "Deluno (Main)",
    queue_row_count: 1,
    managers_consulted: 1,
    managers_reporting: 1,
    managers_without_queue_signal: [],
    reasons: ["Deluno (Main) is still importing this file."],
  });

  render(<ProcessingFilesSection />, { wrapper });
  fireEvent.click(await screen.findByTestId("processing-file-why-held-1"));

  expect(
    await screen.findByTestId("processing-files-notice"),
  ).toHaveTextContent("Deluno (Main) is still importing this file.");
});

it("offers Choose tracks only for held files, and lists a fresh probe with the rules' verdict", async () => {
  asOperator();
  vi.spyOn(api, "fetchProcessingFiles").mockResolvedValue(
    page({
      files: [
        file({ id: 1, status: "on_hold" }),
        file({ id: 2, status: "unprocessed" }),
      ],
    }),
  );
  vi.spyOn(api, "fetchProcessingFileTracks").mockResolvedValue({
    file_id: 1,
    relative_path: "Some Film/film.mkv",
    media_scope: "movie",
    source_fingerprint: {
      device: 0,
      inode: 0,
      size_bytes: 100,
      modified_time_ns: 1,
    },
    streams: [
      {
        index: 0,
        type: "video",
        codec: "h264",
        language: null,
        title: null,
        channels: null,
        default: true,
        forced: false,
        rule_would_keep: true,
        rule_reason: "Kept as the video track.",
      },
      {
        index: 1,
        type: "audio",
        codec: "aac",
        language: "eng",
        title: null,
        channels: 2,
        default: true,
        forced: false,
        rule_would_keep: true,
        rule_reason:
          "Kept: selected as the best audio track (eng aac 2 ch (stream 1)).",
      },
      {
        index: 2,
        type: "audio",
        codec: "aac",
        language: "jpn",
        title: null,
        channels: 2,
        default: false,
        forced: false,
        rule_would_keep: false,
        rule_reason:
          "Removed: not selected (eng aac 2 ch (stream 1) was kept instead).",
      },
    ],
  });

  render(<ProcessingFilesSection />, { wrapper });

  expect(
    screen.queryByTestId("processing-file-choose-tracks-2"),
  ).not.toBeInTheDocument();
  fireEvent.click(await screen.findByTestId("processing-file-choose-tracks-1"));

  const panel = await screen.findByTestId("choose-tracks-panel");
  expect(panel).toHaveTextContent("eng");
  expect(panel).toHaveTextContent("jpn");
  expect(panel).toHaveTextContent("Kept: selected as the best audio track");
  // Seeded from the rules: the English track (the winner) starts checked, the Japanese one does not.
  expect(screen.getByTestId("choose-tracks-keep-1")).toBeChecked();
  expect(screen.getByTestId("choose-tracks-keep-2")).not.toBeChecked();
});

it("queues a hand-picked track choice and shows the confirmation", async () => {
  asOperator();
  vi.spyOn(api, "fetchProcessingFiles").mockResolvedValue(
    page({ files: [file({ id: 1, status: "on_hold" })] }),
  );
  vi.spyOn(api, "fetchProcessingFileTracks").mockResolvedValue({
    file_id: 1,
    relative_path: "Some Film/film.mkv",
    media_scope: "movie",
    source_fingerprint: {
      device: 0,
      inode: 0,
      size_bytes: 100,
      modified_time_ns: 1,
    },
    streams: [
      {
        index: 0,
        type: "video",
        codec: "h264",
        language: null,
        title: null,
        channels: null,
        default: true,
        forced: false,
        rule_would_keep: true,
        rule_reason: "Kept as the video track.",
      },
      {
        index: 1,
        type: "audio",
        codec: "aac",
        language: "eng",
        title: null,
        channels: 2,
        default: true,
        forced: false,
        rule_would_keep: true,
        rule_reason: "Kept: selected as the best audio track.",
      },
    ],
  });
  const postManualPlan = vi
    .spyOn(api, "postProcessingManualPlan")
    .mockResolvedValue({
      ok: true,
      job_id: 42,
      dedupe_key: "processing.file.remux_pass.v1:manual-plan:1:abc",
      job_kind: "processing.file.remux_pass.v1",
    });

  render(<ProcessingFilesSection />, { wrapper });
  fireEvent.click(await screen.findByTestId("processing-file-choose-tracks-1"));
  await screen.findByTestId("choose-tracks-panel");
  fireEvent.click(screen.getByTestId("choose-tracks-submit"));

  await waitFor(() =>
    expect(postManualPlan).toHaveBeenCalledWith(1, {
      keep: [
        { index: 0, default: false, forced: false },
        { index: 1, default: true, forced: false },
      ],
      order: [0, 1],
    }),
  );
  expect(
    await screen.findByTestId("processing-files-notice"),
  ).toHaveTextContent("Queued your track choice for Some Film/film.mkv");
});

it("opens a processing record and offers it as a download", async () => {
  asOperator();
  vi.spyOn(api, "fetchProcessingFiles").mockResolvedValue(
    page({ files: [file({ id: 1, status: "processed" })] }),
  );
  vi.spyOn(api, "fetchProcessingFileLog").mockResolvedValue({
    file_id: 1,
    relative_path: "Some Film/film.mkv",
    retention_days: 90,
    entries: [
      {
        id: 5,
        recorded_at: "2026-08-26T14:00:00Z",
        outcome: "live_output_written",
        title: "Remuxed Some Film",
        library_name: "Movies",
        story: [],
        detail: {
          source_path: "E:/Completed/Some Film/film.mkv",
          output_path: "F:/Some Film/film.mkv",
          output_validation: "Passed: playable video and audio were found.",
          cleanup_result: "Source removed after the output was verified.",
          ffmpeg_argv: ["ffmpeg", "-i", "in.mkv"],
        },
      },
    ],
  });

  render(<ProcessingFilesSection />, { wrapper });
  fireEvent.click(await screen.findByTestId("processing-file-log-1"));

  const panel = await screen.findByTestId("processing-file-log-panel");
  expect(panel).toHaveTextContent("live output written");
  expect(panel).toHaveTextContent("kept for 90 days");
  expect(panel).toHaveTextContent("Output validation");
  expect(panel).toHaveTextContent("Source cleanup");
  expect(panel).toHaveTextContent("Technical record");
  expect(panel).not.toHaveTextContent("Ffmpeg Argv");
  expect(screen.getByTestId("processing-file-log-download")).toHaveAttribute(
    "href",
    "/api/v1/processing/files/1/log/download",
  );
});

it("says zero retention keeps records forever rather than showing a bare 0", async () => {
  asOperator();
  vi.spyOn(api, "fetchProcessingFiles").mockResolvedValue(
    page({ files: [file({ id: 1, status: "processed" })] }),
  );
  vi.spyOn(api, "fetchProcessingFileLog").mockResolvedValue({
    file_id: 1,
    relative_path: "Some Film/film.mkv",
    retention_days: 0,
    entries: [
      {
        id: 5,
        recorded_at: "2026-08-26T14:00:00Z",
        outcome: "live_output_written",
        title: "",
        library_name: "Movies",
        story: [],
        detail: {},
      },
    ],
  });

  render(<ProcessingFilesSection />, { wrapper });
  fireEvent.click(await screen.findByTestId("processing-file-log-1"));

  expect(
    await screen.findByTestId("processing-file-log-panel"),
  ).toHaveTextContent("kept forever");
});

it("explains an empty record instead of opening a blank panel", async () => {
  asOperator();
  vi.spyOn(api, "fetchProcessingFiles").mockResolvedValue(
    page({ files: [file({ id: 1, status: "unprocessed" })] }),
  );
  vi.spyOn(api, "fetchProcessingFileLog").mockResolvedValue({
    file_id: 1,
    relative_path: "Some Film/film.mkv",
    retention_days: 90,
    entries: [],
  });

  render(<ProcessingFilesSection />, { wrapper });
  fireEvent.click(await screen.findByTestId("processing-file-log-1"));

  expect(
    await screen.findByTestId("processing-files-notice"),
  ).toHaveTextContent(/has not processed this file yet/);
  expect(
    screen.queryByTestId("processing-file-log-panel"),
  ).not.toBeInTheDocument();
});

it("shows each device's Direct Play verdict in words, with the reasons", async () => {
  asOperator();
  vi.spyOn(api, "fetchProcessingFiles").mockResolvedValue(
    page({
      files: [
        file({
          id: 7,
          direct_play: [
            {
              device_id: "apple_tv_4k",
              device_name: "Apple TV 4K",
              verdict: "yes",
              reasons: [],
            },
            {
              device_id: "iphone",
              device_name: "iPhone",
              verdict: "no",
              reasons: ["cannot play DTS audio"],
            },
            {
              device_id: "lg_webos",
              device_name: "LG TV",
              verdict: "maybe",
              reasons: ["may not play Dolby TrueHD audio on some tracks"],
            },
            {
              device_id: "roku",
              device_name: "Roku",
              verdict: "unknown",
              reasons: [],
            },
          ],
        }),
      ],
    }),
  );

  render(<ProcessingFilesSection />, { wrapper });

  const badge = await screen.findByTestId("processing-file-direct-play-7");
  expect(badge).toHaveTextContent(
    "Direct Play: Apple TV 4K ✓ yes · iPhone ✗ no (DTS audio) · LG TV ? maybe (may not play Dolby TrueHD audio on some tracks) · Roku (not measured yet)",
  );
  // The verdict is carried in words for screen readers, not only by the mark or its colour.
  expect(within(badge).getByText(/^\s*yes$/)).toHaveClass("sr-only");
  expect(within(badge).getByText(/^\s*no$/)).toHaveClass("sr-only");
  expect(within(badge).getByText(/^\s*maybe$/)).toHaveClass("sr-only");
  // Full reasons on hover, and in a disclosure for keyboard and touch.
  expect(within(badge).getByTitle(/^iPhone/)).toHaveAttribute(
    "title",
    "iPhone cannot play it directly, so the media server will convert it: cannot play DTS audio.",
  );
  fireEvent.click(within(badge).getByText("Why"));
  expect(
    within(badge).getByText(
      "LG TV may not play it directly, so the media server may convert it: may not play Dolby TrueHD audio on some tracks.",
    ),
  ).toBeVisible();
  // Information only: nothing on the row offers to change the file for a device.
  expect(
    screen.queryByRole("button", { name: /convert|compatible|direct play/i }),
  ).not.toBeInTheDocument();
});

it("shows no Direct Play line when no devices are chosen", async () => {
  asOperator();
  vi.spyOn(api, "fetchProcessingFiles").mockResolvedValue(
    page({ files: [file({ id: 7, direct_play: [] })] }),
  );

  render(<ProcessingFilesSection />, { wrapper });

  await screen.findByTestId("processing-file-7");
  expect(
    screen.queryByTestId("processing-file-direct-play-7"),
  ).not.toBeInTheDocument();
  expect(screen.queryByText(/Direct Play/)).not.toBeInTheDocument();
});
