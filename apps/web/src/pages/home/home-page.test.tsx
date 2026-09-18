import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";

import * as filesApi from "../../lib/processing/files-api";
import * as jobsApi from "../../lib/processing/jobs-inspection/api";
import type { ProcessingFile } from "../../lib/processing/files-api";
import * as librariesApi from "../../lib/processing/libraries-api";
import * as statsApi from "../../lib/processing/overview-stats-api";
import * as readinessApi from "../../lib/system/readiness-api";
import { HomePage } from "./home-page";

function file(over: Partial<ProcessingFile> = {}): ProcessingFile {
  return {
    id: 1,
    library_id: 1,
    library_name: "Films 4K",
    relative_path: "movies/Arrival.2016.2160p.mkv",
    status: "unprocessed",
    status_reason: "Waiting for a free lane.",
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

type Surroundings = {
  libraries?: { enabled: boolean; watched_folder: string }[];
  failedJobs?: number;
  workerDetail?: string | null;
};

function mount(
  files: ProcessingFile[],
  counts: Record<string, number> = {},
  surroundings: Surroundings = {},
): void {
  vi.spyOn(filesApi, "fetchProcessingFiles").mockResolvedValue({
    files,
    status_counts: counts,
    returned: files.length,
    limit: 200,
  });
  vi.spyOn(statsApi, "fetchProcessingOverviewStats").mockResolvedValue({
    window_days: 1,
    files_processed: 48,
    files_failed: 0,
    output_written_count: 48,
    already_optimized_count: 0,
    net_space_saved_bytes: 1024 * 1024 * 1024,
    net_space_saved_percent: 12.5,
  } as never);
  vi.spyOn(librariesApi, "fetchProcessingLibraries").mockResolvedValue(
    (surroundings.libraries ?? [
      { enabled: true, watched_folder: "/downloads/complete" },
    ]) as never,
  );
  vi.spyOn(jobsApi, "fetchProcessingJobsInspection").mockResolvedValue({
    jobs: Array.from({ length: surroundings.failedJobs ?? 0 }, (_, i) => ({
      id: i + 1,
      status: "failed",
    })),
    default_recent_slice: false,
  } as never);
  vi.spyOn(readinessApi, "fetchSystemReadiness").mockResolvedValue({
    ready: !surroundings.workerDetail,
    version: "3.0.0",
    status: surroundings.workerDetail ? "failed" : "ready",
    startup_seconds: 1,
    steps: [],
    worker_health: surroundings.workerDetail
      ? [
          {
            module: "processing",
            expected_workers: 1,
            active_workers: 0,
            stale_workers: 1,
            stopped_workers: 0,
            status: "degraded",
            detail: surroundings.workerDetail,
          },
        ]
      : [],
  });

  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
  render(<HomePage />, { wrapper });
}

afterEach(() => {
  vi.restoreAllMocks();
});

it("says where the files are, without claiming to know the library", async () => {
  mount([file()], { unprocessed: 12, processing: 3 });

  expect(
    await screen.findByRole("heading", { level: 1, name: "Home" }),
  ).toBeInTheDocument();
  expect(screen.getByText("Arriving")).toBeInTheDocument();
  expect(screen.getByText("Handed back today")).toBeInTheDocument();
  // The subject is custody. "Your library" is a claim this product cannot make.
  expect(screen.queryByText(/your library/i)).not.toBeInTheDocument();
});

it("sizes each band stage by the number of files sitting in it", async () => {
  mount([file()], { unprocessed: 12, processing: 3, on_hold: 0 });

  const stages = await screen.findAllByTestId("home-band-stage");
  const share = (label: string) =>
    stages
      .find((s) => s.textContent?.startsWith(label))
      ?.getAttribute("style") ?? "";

  // 15 files in the band: 12 and 3 by count, an empty stage floored at 6% so it still reads.
  expect(share("Arriving")).toContain("--mm-flow-share: 12");
  expect(share("Working")).toContain("--mm-flow-share: 3");
  expect(share("On hold")).toMatch(
    /--mm-flow-share: 0\.8999|--mm-flow-share: 0\.9/,
  );
  // Each stage opens Files filtered to exactly that status.
  expect(screen.getByRole("link", { name: /Arriving/ })).toHaveAttribute(
    "href",
    "/processing?tab=files&status=unprocessed",
  );
});

it("says so in a sentence rather than drawing an empty band", async () => {
  mount([], {});

  expect(await screen.findByTestId("home-band-empty")).toBeInTheDocument();
  expect(screen.queryByTestId("home-band")).not.toBeInTheDocument();
  // Folders are set, so today's numbers still render.
  expect(screen.getByTestId("home-today")).toBeInTheDocument();
});

it("groups files by library", async () => {
  mount([
    file({ id: 1, library_name: "Films 4K" }),
    file({
      id: 2,
      library_name: "Shows",
      relative_path: "tv/Andor.S01E11.mkv",
    }),
  ]);

  expect(await screen.findByLabelText("Films 4K")).toBeInTheDocument();
  expect(screen.getByLabelText("Shows")).toBeInTheDocument();
});

it("shows what a file is, from the probe", async () => {
  mount([
    file({
      video_codec: "hevc",
      video_height: 2160,
      audio_track_count: 3,
      subtitle_track_count: 2,
    }),
  ]);

  expect(await screen.findByText(/hevc 2160p/)).toBeInTheDocument();
  expect(screen.getByText(/3 audio tracks/)).toBeInTheDocument();
});

it("omits facts for a file nobody has probed yet", async () => {
  mount([file()]);

  await screen.findByTestId("home-row");
  // Null means "not measured" and must not render as a zero.
  expect(screen.queryByText(/0 audio tracks/)).not.toBeInTheDocument();
});

it("draws a progress bar for the pass that is running", async () => {
  mount([
    file({
      status: "processing",
      progress_percent: 61,
      progress_eta_seconds: 240,
    }),
  ]);

  const bar = await screen.findByRole("progressbar");
  expect(bar).toHaveAttribute("aria-valuenow", "61");
  expect(screen.getByText(/61%/)).toBeInTheDocument();
  expect(screen.getByText(/4m left/)).toBeInTheDocument();
});

it("shows a held file as the guardrail working, naming who holds it", async () => {
  mount([
    file({
      status: "blocked_upstream",
      blocked_by_connection: "Deluno",
      status_reason: "Deluno is importing this file.",
    }),
  ]);

  expect(await screen.findByText(/Deluno is importing it/)).toBeInTheDocument();
});

it("says what being stuck actually costs", async () => {
  mount([file({ status: "processing_failed" })]);

  expect(
    await screen.findByText(/1 file is stuck in Weir's hands/),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/will not see these until they are dealt with/),
  ).toBeInTheDocument();
});

it("reads as finished rather than broken when Weir is holding nothing", async () => {
  mount([]);

  await waitFor(() => {
    expect(screen.getByText("Nothing held right now")).toBeInTheDocument();
  });
  expect(screen.queryByTestId("home-row")).not.toBeInTheDocument();
});

it("opens a file's story from its row", async () => {
  const fetchLog = vi
    .spyOn(filesApi, "fetchProcessingFileLog")
    .mockResolvedValue({
      file_id: 1,
      relative_path: "movies/Arrival.2016.2160p.mkv",
      retention_days: 90,
      entries: [
        {
          id: 1,
          recorded_at: "2026-09-16T14:02:00Z",
          outcome: "live_output_written",
          title: "Remuxed Arrival",
          library_name: "Films 4K",
          detail: {},
          story: [
            {
              heading: "Picked up",
              sentence:
                "Weir took this file as a film in the Films 4K library.",
              tone: "neutral",
            },
          ],
        },
      ],
    });
  mount([file({ id: 1 })]);

  fireEvent.click(
    await screen.findByRole("button", { name: "Arrival.2016.2160p.mkv" }),
  );

  expect(await screen.findByRole("dialog")).toBeInTheDocument();
  expect(await screen.findByText("Picked up")).toBeInTheDocument();
  expect(fetchLog).toHaveBeenCalledWith(1);
});

it("shows the Direct Play badge on a row, and the full reasons in the file's story", async () => {
  vi.spyOn(filesApi, "fetchProcessingFileLog").mockResolvedValue({
    file_id: 1,
    relative_path: "movies/Arrival.2016.2160p.mkv",
    retention_days: 90,
    entries: [],
  });
  mount([
    file({
      id: 1,
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
          reasons: ["cannot play DTS audio", "cannot play MKV files"],
        },
      ],
    }),
  ]);

  const badge = await screen.findByTestId("home-direct-play-1");
  expect(badge).toHaveTextContent(
    "Direct Play: Apple TV 4K ✓ yes · iPhone ✗ no (DTS audio, +1 more)",
  );

  fireEvent.click(
    screen.getByRole("button", { name: "Arrival.2016.2160p.mkv" }),
  );
  const story = await screen.findByTestId("file-story-direct-play");
  expect(story).toHaveTextContent(
    "iPhone cannot play it directly, so the media server will convert it: cannot play DTS audio; cannot play MKV files.",
  );
  expect(story).toHaveTextContent(
    "Information only. Weir never changes a file because of this.",
  );
});

it("shows no Direct Play badge when no devices are chosen", async () => {
  mount([file({ id: 1, direct_play: [] })]);

  await screen.findByTestId("home-row");
  expect(screen.queryByTestId("home-direct-play-1")).not.toBeInTheDocument();
  expect(screen.queryByText(/Direct Play/)).not.toBeInTheDocument();
});

it("asks nothing of a healthy install", async () => {
  mount([file()]);

  await screen.findByTestId("home-row");
  expect(screen.queryByTestId("home-notices")).not.toBeInTheDocument();
});

it("says there is nothing to watch before any watched folder is set (#459)", async () => {
  mount([], {}, { libraries: [{ enabled: false, watched_folder: "/x" }] });

  // The sentence now leads an interrupt line above the band, so it is matched loosely;
  // where its link goes is the guarantee, and that is asserted exactly.
  expect(await screen.findByText(/Nothing to watch yet/)).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: /Set up a library/ }),
  ).toHaveAttribute("href", "/processing?tab=libraries");
});

it("draws no band of zeroes before any watched folder is set", async () => {
  mount([], {}, { libraries: [{ enabled: false, watched_folder: "/x" }] });

  // A fresh install must not lead with six empty stages: the setup interrupt wins outright.
  await screen.findByText(/Nothing to watch yet/);
  expect(screen.queryByTestId("home-band")).not.toBeInTheDocument();
  expect(screen.queryByTestId("home-today")).not.toBeInTheDocument();
});

it("carries the old dashboard's stopped-worker and failed-job warnings (#459)", async () => {
  mount(
    [],
    {},
    {
      failedJobs: 2,
      workerDetail:
        "Weir is not processing new work because 1 worker slot(s) stopped responding.",
    },
  );

  expect(
    await screen.findByText(/Background work has stopped/),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/1 worker slot\(s\) stopped responding/),
  ).toBeInTheDocument();
  expect(await screen.findByText(/2 jobs failed/)).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: /Review failed jobs/ }),
  ).toHaveAttribute("href", "/processing?tab=jobs&status=failed");
});
