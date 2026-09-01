import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";

import * as api from "../../lib/refiner/files-api";
import * as remuxApi from "../../lib/refiner/file-remux-pass-api";
import type {
  RefinerFile,
  RefinerFilesPage,
} from "../../lib/refiner/files-api";
import * as librariesApi from "../../lib/refiner/libraries-api";
import * as authQueries from "../../lib/auth/queries";
import * as pauseApi from "../../lib/suite/pause-api";
import { RefinerFilesSection } from "./refiner-files-section";

function file(over: Partial<RefinerFile> = {}): RefinerFile {
  return {
    id: 1,
    library_id: 1,
    library_name: "Movies",
    relative_path: "Some Film/film.mkv",
    status: "unprocessed",
    status_reason: "Ready for Refiner to process as part of Movies.",
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
    hold_until: null,
    size_changed_at: null,
    created_at: "2026-09-01T08:00:00Z",
    updated_at: "2026-09-01T08:05:00Z",
    last_seen_at: null,
    last_attempt_at: null,
    ...over,
  };
}

function page(over: Partial<RefinerFilesPage> = {}): RefinerFilesPage {
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
  vi.spyOn(librariesApi, "fetchRefinerLibraries").mockResolvedValue([]);
  vi.spyOn(pauseApi, "fetchSuitePause").mockResolvedValue({
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
  vi.spyOn(api, "fetchRefinerFiles").mockResolvedValue(
    page({
      files: [
        file({
          status: "blocked_upstream",
          status_reason:
            "Deluno (Main) is still importing this file, so MediaMop left it alone for now.",
          blocked_by_connection: "Deluno (Main)",
        }),
      ],
      status_counts: { blocked_upstream: 1 },
    }),
  );

  render(<RefinerFilesSection />, { wrapper });

  expect(
    await screen.findByText(/Deluno \(Main\) is still importing this file/),
  ).toBeInTheDocument();
});

it("shows first-seen, last-check, and processing-attempt timestamps on every file", async () => {
  asOperator();
  vi.spyOn(api, "fetchRefinerFiles").mockResolvedValue(
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

  render(<RefinerFilesSection />, { wrapper });

  const timeline = await screen.findByTestId("refiner-file-timestamps-1");
  expect(timeline).toHaveTextContent("First seen");
  expect(timeline).toHaveTextContent("Last checked");
  expect(timeline).toHaveTextContent("Last processing attempt");
  expect(timeline).not.toHaveTextContent("Not recorded");
});

it("treats timezone-less backend timestamps as UTC in relative ages", async () => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-09-01T02:04:00Z"));
  asOperator();
  vi.spyOn(api, "fetchRefinerFiles").mockResolvedValue(
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

  render(<RefinerFilesSection />, { wrapper });

  const timeline = await screen.findByTestId("refiner-file-timestamps-1");
  expect(timeline).toHaveTextContent("45 min ago");
  expect(timeline).toHaveTextContent("just now");
  expect(timeline).toHaveTextContent("44 min ago");
  expect(timeline).not.toHaveTextContent("10 hr ago");
});

it("shows a bucket for every state, including empty ones", async () => {
  asOperator();
  vi.spyOn(api, "fetchRefinerFiles").mockResolvedValue(page());

  render(<RefinerFilesSection />, { wrapper });

  expect(
    await screen.findByTestId("refiner-files-bucket-on_hold"),
  ).toHaveTextContent("On hold (0)");
  expect(
    screen.getByTestId("refiner-files-bucket-out_of_schedule"),
  ).toBeInTheDocument();
  expect(
    screen.getByTestId("refiner-files-bucket-disabled"),
  ).toBeInTheDocument();
});

it("labels paused work as paused instead of claiming its schedule is closed", async () => {
  asOperator();
  vi.mocked(pauseApi.fetchSuitePause).mockResolvedValue({
    paused: true,
    paused_until: null,
    scan_while_paused: true,
    reason: "Processing is paused until it is resumed.",
    in_flight_policy: "Work already running finishes.",
  });
  vi.spyOn(api, "fetchRefinerFiles").mockResolvedValue(
    page({
      files: [
        file({
          status: "out_of_schedule",
          status_reason:
            "Processing is paused. MediaMop will start work again when you resume it.",
        }),
      ],
      status_counts: { out_of_schedule: 1 },
    }),
  );

  render(<RefinerFilesSection />, { wrapper });

  expect(await screen.findByText("Paused")).toBeInTheDocument();
  expect(screen.getByText("Processing is paused.")).toBeInTheDocument();
  expect(screen.getByText(/Use Resume at the top/)).toBeInTheDocument();
  expect(
    screen.queryByText("This library is outside its schedule."),
  ).not.toBeInTheDocument();
});

it("asks for a re-check when a saved pause reason is stale", async () => {
  asOperator();
  vi.spyOn(api, "fetchRefinerFiles").mockResolvedValue(
    page({
      files: [
        file({
          status: "out_of_schedule",
          status_reason:
            "Processing is paused. MediaMop will start work again when you resume it.",
        }),
      ],
      status_counts: { out_of_schedule: 1 },
    }),
  );

  render(<RefinerFilesSection />, { wrapper });

  expect(await screen.findAllByText(/Needs re-check/)).toHaveLength(2);
  expect(screen.getByText("Refresh this file's status.")).toBeInTheDocument();
  expect(screen.getByText(/Use Check again/)).toBeInTheDocument();
  expect(screen.queryByText("Processing is paused.")).not.toBeInTheDocument();
  expect(screen.getByText("Needs action").parentElement).toHaveTextContent("1");
});

it("filters by bucket", async () => {
  asOperator();
  const fetchFiles = vi
    .spyOn(api, "fetchRefinerFiles")
    .mockResolvedValue(page());

  render(<RefinerFilesSection />, { wrapper });
  fireEvent.click(await screen.findByTestId("refiner-files-bucket-on_hold"));

  await waitFor(() => {
    expect(fetchFiles).toHaveBeenCalledWith(
      expect.objectContaining({ file_status: "on_hold" }),
    );
  });
});

it("says removing a file only removes the record", async () => {
  asOperator();
  vi.spyOn(api, "fetchRefinerFiles").mockResolvedValue(page());

  render(<RefinerFilesSection />, { wrapper });

  const button = await screen.findByTestId("refiner-file-forget-1");
  expect(button).toHaveAttribute(
    "title",
    expect.stringContaining("file on disk is untouched"),
  );
});

it("does not offer removal to a viewer", async () => {
  vi.spyOn(authQueries, "useMeQuery").mockReturnValue({
    data: { role: "viewer" },
  } as ReturnType<typeof authQueries.useMeQuery>);
  vi.spyOn(librariesApi, "fetchRefinerLibraries").mockResolvedValue([]);
  vi.spyOn(api, "fetchRefinerFiles").mockResolvedValue(page());

  render(<RefinerFilesSection />, { wrapper });

  expect(await screen.findByText("Some Film/film.mkv")).toBeInTheDocument();
  expect(screen.queryByTestId("refiner-file-forget-1")).not.toBeInTheDocument();
});

it("explains an empty list rather than showing nothing", async () => {
  asOperator();
  vi.spyOn(api, "fetchRefinerFiles").mockResolvedValue(
    page({ files: [], status_counts: {}, returned: 0 }),
  );

  render(<RefinerFilesSection />, { wrapper });

  expect(await screen.findByText(/No files match/)).toBeInTheDocument();
});

it("shows a held file's release time so the wait is not open-ended", async () => {
  asOperator();
  vi.spyOn(api, "fetchRefinerFiles").mockResolvedValue(
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

  render(<RefinerFilesSection />, { wrapper });

  expect(
    await screen.findByTestId("refiner-file-hold-until-1"),
  ).toHaveTextContent(/Ready in about 30s/);
});

it("invents no release time when the wait is on a writer rather than the clock", async () => {
  asOperator();
  vi.spyOn(api, "fetchRefinerFiles").mockResolvedValue(
    page({
      files: [
        file({
          status: "on_hold",
          status_reason: "MediaMop could not open this file for reading.",
          hold_until: null,
        }),
      ],
    }),
  );

  render(<RefinerFilesSection />, { wrapper });

  expect(
    await screen.findByText(/could not open this file for reading/),
  ).toBeInTheDocument();
  expect(
    screen.queryByTestId("refiner-file-hold-until-1"),
  ).not.toBeInTheDocument();
});

it("offers move to top only for work that has not started", async () => {
  asOperator();
  vi.spyOn(api, "fetchRefinerFiles").mockResolvedValue(
    page({
      files: [
        file({ id: 1, status: "unprocessed" }),
        file({ id: 2, status: "processing", relative_path: "Other/other.mkv" }),
      ],
    }),
  );

  render(<RefinerFilesSection />, { wrapper });

  expect(
    await screen.findByTestId("refiner-file-move-to-top-1"),
  ).toBeInTheDocument();
  // A running file cannot be started earlier; a button here would be a lie.
  expect(
    screen.queryByTestId("refiner-file-move-to-top-2"),
  ).not.toBeInTheDocument();
});

it("shows the server's own words about whether the move happened", async () => {
  asOperator();
  vi.spyOn(api, "fetchRefinerFiles").mockResolvedValue(
    page({ files: [file({ id: 1, status: "unprocessed" })] }),
  );
  vi.spyOn(api, "moveRefinerFileToTop").mockResolvedValue({
    moved: false,
    detail: "There is no queued work for this file to move.",
  });

  render(<RefinerFilesSection />, { wrapper });
  fireEvent.click(await screen.findByTestId("refiner-file-move-to-top-1"));

  expect(await screen.findByTestId("refiner-files-notice")).toHaveTextContent(
    "There is no queued work for this file to move.",
  );
});

it("offers a retry on a failed file and shows what the server said", async () => {
  asOperator();
  vi.spyOn(api, "fetchRefinerFiles").mockResolvedValue(
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
  vi.spyOn(api, "requeueRefinerFile").mockResolvedValue({
    requeued: 1,
    skipped: 0,
    detail:
      "Queued again by hand. It starts as soon as there is capacity for it.",
  });

  render(<RefinerFilesSection />, { wrapper });
  fireEvent.click(await screen.findByTestId("refiner-file-requeue-1"));

  expect(await screen.findByTestId("refiner-files-notice")).toHaveTextContent(
    /Queued again by hand/,
  );
});

it("passes an edge-case file through unchanged only after explaining source cleanup", async () => {
  asOperator();
  vi.spyOn(api, "fetchRefinerFiles").mockResolvedValue(
    page({
      files: [file({ id: 1, status: "processing_failed" })],
      status_counts: { processing_failed: 1 },
    }),
  );
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
  const enqueue = vi
    .spyOn(remuxApi, "postRefinerFileRemuxPassEnqueue")
    .mockResolvedValue({
      ok: true,
      job_id: 44,
      dedupe_key: "pass-through-44",
      job_kind: "refiner.file.remux_pass.v1",
    });

  render(<RefinerFilesSection />, { wrapper });
  fireEvent.click(await screen.findByTestId("refiner-file-pass-through-1"));

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
  expect(await screen.findByTestId("refiner-files-notice")).toHaveTextContent(
    /Queued to pass through unchanged/,
  );
});

it("does not offer a retry on a file that has not failed", async () => {
  asOperator();
  vi.spyOn(api, "fetchRefinerFiles").mockResolvedValue(
    page({ files: [file({ id: 1, status: "unprocessed" })] }),
  );

  render(<RefinerFilesSection />, { wrapper });

  await screen.findByText("Some Film/film.mkv");
  expect(
    screen.queryByTestId("refiner-file-requeue-1"),
  ).not.toBeInTheDocument();
});

it("asks the managers why a file is held and shows their own words", async () => {
  asOperator();
  vi.spyOn(api, "fetchRefinerFiles").mockResolvedValue(
    page({ files: [file({ id: 1, status: "blocked_upstream" })] }),
  );
  vi.spyOn(api, "fetchRefinerWhyHeld").mockResolvedValue({
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

  render(<RefinerFilesSection />, { wrapper });
  fireEvent.click(await screen.findByTestId("refiner-file-why-held-1"));

  expect(await screen.findByTestId("refiner-files-notice")).toHaveTextContent(
    "Deluno (Main) is still importing this file.",
  );
});

it("opens a processing record and offers it as a download", async () => {
  asOperator();
  vi.spyOn(api, "fetchRefinerFiles").mockResolvedValue(
    page({ files: [file({ id: 1, status: "processed" })] }),
  );
  vi.spyOn(api, "fetchRefinerFileLog").mockResolvedValue({
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

  render(<RefinerFilesSection />, { wrapper });
  fireEvent.click(await screen.findByTestId("refiner-file-log-1"));

  const panel = await screen.findByTestId("refiner-file-log-panel");
  expect(panel).toHaveTextContent("live output written");
  expect(panel).toHaveTextContent("kept for 90 days");
  expect(panel).toHaveTextContent("Output validation");
  expect(panel).toHaveTextContent("Source cleanup");
  expect(panel).toHaveTextContent("Technical record");
  expect(panel).not.toHaveTextContent("Ffmpeg Argv");
  expect(screen.getByTestId("refiner-file-log-download")).toHaveAttribute(
    "href",
    "/api/v1/refiner/files/1/log/download",
  );
});

it("says zero retention keeps records forever rather than showing a bare 0", async () => {
  asOperator();
  vi.spyOn(api, "fetchRefinerFiles").mockResolvedValue(
    page({ files: [file({ id: 1, status: "processed" })] }),
  );
  vi.spyOn(api, "fetchRefinerFileLog").mockResolvedValue({
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
        detail: {},
      },
    ],
  });

  render(<RefinerFilesSection />, { wrapper });
  fireEvent.click(await screen.findByTestId("refiner-file-log-1"));

  expect(await screen.findByTestId("refiner-file-log-panel")).toHaveTextContent(
    "kept forever",
  );
});

it("explains an empty record instead of opening a blank panel", async () => {
  asOperator();
  vi.spyOn(api, "fetchRefinerFiles").mockResolvedValue(
    page({ files: [file({ id: 1, status: "unprocessed" })] }),
  );
  vi.spyOn(api, "fetchRefinerFileLog").mockResolvedValue({
    file_id: 1,
    relative_path: "Some Film/film.mkv",
    retention_days: 90,
    entries: [],
  });

  render(<RefinerFilesSection />, { wrapper });
  fireEvent.click(await screen.findByTestId("refiner-file-log-1"));

  expect(await screen.findByTestId("refiner-files-notice")).toHaveTextContent(
    /has not processed this file yet/,
  );
  expect(
    screen.queryByTestId("refiner-file-log-panel"),
  ).not.toBeInTheDocument();
});
