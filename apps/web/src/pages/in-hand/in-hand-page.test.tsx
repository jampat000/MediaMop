import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";

import * as filesApi from "../../lib/refiner/files-api";
import type { RefinerFile } from "../../lib/refiner/files-api";
import * as librariesApi from "../../lib/refiner/libraries-api";
import * as statsApi from "../../lib/refiner/overview-stats-api";
import { InHandPage } from "./in-hand-page";

function file(over: Partial<RefinerFile> = {}): RefinerFile {
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

function mount(
  files: RefinerFile[],
  counts: Record<string, number> = {},
): void {
  vi.spyOn(filesApi, "fetchRefinerFiles").mockResolvedValue({
    files,
    status_counts: counts,
    returned: files.length,
    limit: 200,
  });
  vi.spyOn(statsApi, "fetchRefinerOverviewStats").mockResolvedValue({
    window_days: 1,
    files_processed: 48,
    files_failed: 0,
    output_written_count: 48,
    already_optimized_count: 0,
    net_space_saved_bytes: 1024 * 1024 * 1024,
    net_space_saved_percent: 12.5,
  } as never);
  vi.spyOn(librariesApi, "fetchRefinerLibraries").mockResolvedValue(
    [] as never,
  );

  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
  render(<InHandPage />, { wrapper });
}

afterEach(() => {
  vi.restoreAllMocks();
});

it("says where the files are, without claiming to know the library", async () => {
  mount([file()], { unprocessed: 12, processing: 3 });

  expect(await screen.findByText("In hand")).toBeInTheDocument();
  expect(screen.getByText("Arriving")).toBeInTheDocument();
  expect(screen.getByText("Handed back today")).toBeInTheDocument();
  // The subject is custody. "Your library" is a claim this product cannot make.
  expect(screen.queryByText(/your library/i)).not.toBeInTheDocument();
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

  await screen.findByTestId("in-hand-row");
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
    await screen.findByText(/1 file is stuck in MediaMop's hands/),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/will not see these until they are dealt with/),
  ).toBeInTheDocument();
});

it("reads as finished rather than broken when nothing is in hand", async () => {
  mount([]);

  await waitFor(() => {
    expect(screen.getByText("Nothing in hand")).toBeInTheDocument();
  });
  expect(screen.queryByTestId("in-hand-row")).not.toBeInTheDocument();
});
