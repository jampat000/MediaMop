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
import { describe, expect, it, vi } from "vitest";
import type { UserPublic } from "../../lib/api/types";
import { qk } from "../../lib/auth/queries";
import { processingJobsInspectionQueryKey } from "../../lib/processing/jobs-inspection/queries";
import type {
  ProcessingLibrary,
  ProcessingRuleSet,
} from "../../lib/processing/libraries-api";
import { processingFilesKey } from "../../lib/processing/files-queries";
import {
  processingLibrariesKey,
  processingRuleSetsKey,
} from "../../lib/processing/libraries-queries";
import {
  processingOperatorSettingsQueryKey,
  processingOverviewStatsQueryKey,
} from "../../lib/processing/queries";
import * as scanApi from "../../lib/processing/watched-folder-scan-api";
import { ProcessingPage } from "./processing-page";

const operatorMe: UserPublic = { id: 1, username: "alice", role: "operator" };

const englishJapaneseRules = {
  id: 1,
  name: "English first",
  primary_audio_lang: "eng",
  secondary_audio_lang: "jpn",
  tertiary_audio_lang: "",
  default_audio_slot: "primary",
  remove_commentary: true,
  subtitle_mode: "remove_all",
  subtitle_langs_csv: "",
  preserve_forced_subs: true,
  preserve_default_subs: true,
  audio_preference_mode: "preferred_langs_quality",
  used_by_library_count: 1,
  updated_at: "2026-04-11T00:00:00Z",
} as ProcessingRuleSet;

function library(over: Partial<ProcessingLibrary>): ProcessingLibrary {
  return {
    id: 1,
    name: "Movies",
    enabled: true,
    media_type: "movie",
    display_order: 0,
    watched_folder: "",
    work_folder: "",
    output_folder: "",
    scan_interval_seconds: 300,
    rule_set_id: null,
    manager_connection_ids: [],
    active_job_count: 0,
    updated_at: null,
    ...over,
  } as ProcessingLibrary;
}

/** Two film libraries and one TV library: adding a second library of a type is normal. */
const seededLibraries: ProcessingLibrary[] = [
  library({
    id: 1,
    name: "Films",
    watched_folder: "/srv/films/in",
    output_folder: "/srv/films/out",
    rule_set_id: 1,
  }),
  library({ id: 2, name: "4K films", display_order: 1 }),
  library({
    id: 3,
    name: "Shows",
    media_type: "tv",
    display_order: 2,
    scan_interval_seconds: 3600,
  }),
];

function wrap(
  ui: ReactNode,
  client: QueryClient,
  initialEntry = "/processing",
) {
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

function seedProcessingQueries(qc: QueryClient) {
  qc.setQueryData(processingOverviewStatsQueryKey, {
    window_days: 30,
    files_processed: 42,
    files_failed: 1,
    success_rate_percent: 97.7,
    output_written_count: 38,
    already_optimized_count: 4,
    net_space_saved_bytes: 3_221_225_472,
    net_space_saved_percent: 12.5,
  });
  // The lead band is drawn from the file census, not from job counts.
  qc.setQueryData(processingFilesKey({ limit: 1 }), {
    files: [],
    returned: 0,
    limit: 1,
    status_counts: {
      unprocessed: 6,
      on_hold: 2,
      processing: 1,
      processed: 42,
      skipped: 3,
      processing_failed: 1,
      out_of_schedule: 5,
    },
  });
  qc.setQueryData(processingLibrariesKey, seededLibraries);
  qc.setQueryData(processingRuleSetsKey, [englishJapaneseRules]);
  qc.setQueryData(processingOperatorSettingsQueryKey, {
    max_concurrent_files: 1,
    runner_capacity: 4,
    runner_cost_sd: 1,
    runner_cost_720p: 1,
    runner_cost_1080p: 2,
    runner_cost_4k: 4,
    runner_cost_undetermined: 0,
    work_temp_stale_sweep_enabled: true,
    failure_cleanup_enabled: false,
    keep_failed_work_files: false,
    file_log_retention_days: 90,
    verbose_detection_logging: false,
    min_file_age_seconds: 60,
    min_input_file_size_mb: 50,
    minimum_free_disk_space_mb: 5120,
    movie_schedule_enabled: true,
    movie_schedule_hours_limited: false,
    movie_schedule_days: "",
    movie_schedule_start: "00:00",
    movie_schedule_end: "23:59",
    tv_schedule_enabled: true,
    tv_schedule_hours_limited: false,
    tv_schedule_days: "",
    tv_schedule_start: "00:00",
    tv_schedule_end: "23:59",
    schedule_timezone: "UTC",
    updated_at: "2026-04-11T00:00:00Z",
  });
  qc.setQueryData(processingJobsInspectionQueryKey("recent"), {
    jobs: [],
    default_recent_slice: true,
  });
  qc.setQueryData(processingJobsInspectionQueryKey("pending"), { jobs: [] });
  qc.setQueryData(processingJobsInspectionQueryKey("leased"), { jobs: [] });
  qc.setQueryData(processingJobsInspectionQueryKey("failed"), { jobs: [] });
}

function openTab(label: string) {
  fireEvent.click(screen.getByRole("tab", { name: label }));
}

function renderProcessingPage(initialEntry = "/processing") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  seedProcessingQueries(qc);
  qc.setQueryData(qk.me, operatorMe);
  return render(wrap(<ProcessingPage />, qc, initialEntry));
}

describe("ProcessingPage", () => {
  it("renders the Processing page", () => {
    renderProcessingPage();
    expect(screen.getByTestId("processing-scope-page")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 1, name: "Processing" }),
    ).toBeInTheDocument();
    // #568 renamed this tab from "Existing library"; it is the library itself, not a category of file.
    expect(screen.getByRole("tab", { name: "Library" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Existing library" })).toBeNull();
    // #563/#567 put this here to prove no user-visible text says "Refiner", and #578 finished
    // removing the name. It keeps the old spelling on purpose: it is a guard against the name
    // coming back, so renaming it to /Processing/ would assert the page has no title.
    expect(screen.queryByText(/Refiner/)).toBeNull();
  });

  it("Overview is the default tab and links Activity without leaking env keys", () => {
    renderProcessingPage();
    expect(screen.getByTestId("processing-overview-panel")).toBeInTheDocument();
    const overview =
      screen.getByTestId("processing-overview-panel").textContent ?? "";
    expect(overview).toMatch(/Processed/i);
    expect(overview).not.toMatch(/WEIR_/i);
    // Also deliberately the old spelling: the guard is that a raw table identifier never reaches
    // the panel. Matching /jobs/i instead would fire on ordinary prose now the table is `jobs`.
    expect(overview).not.toMatch(/refiner_jobs/i);
    expect(screen.getByRole("link", { name: "Activity" })).toHaveAttribute(
      "href",
      "/activity",
    );
  });

  it("Overview surfaces saved audio/subtitle defaults at a glance", () => {
    renderProcessingPage();
    const card = screen.getByTestId(
      "processing-overview-audio-subtitles-glance",
    );
    expect(card.textContent).toMatch(/Audio & subtitles/i);
    expect(card.textContent).toMatch(/English/i);
    expect(card.textContent).toMatch(/Japanese/i);
    expect(card.textContent).toMatch(/Remove all subtitles/i);
    expect(card.textContent).toMatch(/English first/);
    expect(card.textContent).toMatch(/TV episodes defaults/);
  });

  it("Overview lists every library, including two of the same media type", () => {
    renderProcessingPage();
    const rows = screen.getAllByTestId("processing-overview-library");
    expect(rows.map((row) => row.querySelector("th")?.textContent)).toEqual([
      "FilmsMovies",
      "4K filmsMovies",
      // A name that already says what it is gets no repeated type badge.
      "Shows",
    ]);
    expect(within(rows[0]).getAllByText("Set")).toHaveLength(2);
    expect(within(rows[1]).getAllByText("Not set")).toHaveLength(2);
    expect(rows[2].textContent).toMatch(/Every hour/);
    const attention = screen.getByTestId("processing-overview-needs-attention");
    expect(attention.textContent).toMatch(
      /2 libraries have no watched folder \(4K films, Shows\)/,
    );
    // One contextual panel: attention items replace the setup checklist once a folder is set.
    expect(screen.queryByTestId("processing-guided-setup")).toBeNull();
    expect(screen.queryByText(/Next steps/i)).toBeNull();
  });

  it("Overview leads with the pipeline, then one hero figure and its supporters", () => {
    renderProcessingPage();
    // Rule 1: a band across the top, one segment per pipeline stage, each a filter.
    const stages = screen.getAllByTestId("processing-overview-flow-stage");
    expect(stages).toHaveLength(6);
    expect(stages.map((stage) => stage.textContent)).toEqual([
      expect.stringContaining("Waiting"),
      expect.stringContaining("On hold"),
      expect.stringContaining("Processing"),
      expect.stringContaining("Done"),
      expect.stringContaining("Skipped"),
      expect.stringContaining("Failed"),
    ]);
    // Wider stage for the bigger number: the share is the count, floored.
    expect(stages[3].getAttribute("style")).toMatch(/--mm-flow-share: 42/);
    // The two operator facts that used to sit in the stats card are still on the page.
    const caption = screen.getByTestId("processing-overview-flow-caption");
    expect(caption.textContent).toMatch(/not changed for 60 seconds/i);
    expect(caption.textContent).toMatch(/Up to 1 at once/i);
    // Files in states the band does not draw are counted, not hidden.
    expect(caption.textContent).toMatch(
      /5 more in states the band does not show/i,
    );

    // Rule 2: one hero figure, narrow supporters beside it.
    const figures = screen.getByTestId("processing-overview-last-30-days");
    expect(figures.textContent).toMatch(/Processed/i);
    expect(figures.textContent).toMatch(/42/);
    expect(figures.textContent).toMatch(/Success rate/i);
    expect(figures.textContent).toMatch(/97.7%/);
    expect(figures.textContent).toMatch(/Reclaimed/i);
    expect(figures.textContent).toMatch(/3.0 GB/);
    expect(figures.querySelectorAll(".mm-figure--hero")).toHaveLength(1);
  });

  it("a lead-band stage opens Files filtered to that stage", async () => {
    renderProcessingPage();
    fireEvent.click(screen.getAllByTestId("processing-overview-flow-stage")[5]);
    await waitFor(() =>
      expect(screen.getByRole("tab", { name: "Files" })).toHaveAttribute(
        "aria-selected",
        "true",
      ),
    );
  });

  it("Overview shows a dash for the success rate before any job has finished", () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    seedProcessingQueries(qc);
    qc.setQueryData(processingOverviewStatsQueryKey, {
      window_days: 30,
      files_processed: 0,
      files_failed: 0,
      success_rate_percent: 0,
      output_written_count: 0,
      already_optimized_count: 0,
      net_space_saved_bytes: 0,
      net_space_saved_percent: 0,
    });
    qc.setQueryData(qk.me, operatorMe);
    render(wrap(<ProcessingPage />, qc));
    const last30 = screen.getByTestId("processing-overview-last-30-days");
    expect(last30.textContent).toMatch(/Success rate—/);
    expect(last30.textContent).not.toMatch(/0%/);
  });

  it("a band of six zeroes never ships: an empty census says so in words", () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    seedProcessingQueries(qc);
    qc.setQueryData(processingFilesKey({ limit: 1 }), {
      files: [],
      returned: 0,
      limit: 1,
      status_counts: {},
    });
    qc.setQueryData(qk.me, operatorMe);
    render(wrap(<ProcessingPage />, qc));
    expect(screen.queryByTestId("processing-overview-flow")).toBeNull();
    expect(
      screen.getByTestId("processing-overview-flow-empty").textContent,
    ).toMatch(/no files in hand yet/i);
    // The figures still carry the month, so the page is not blank.
    expect(
      screen.getByTestId("processing-overview-last-30-days").textContent,
    ).toMatch(/Processed/i);
  });

  it("Overview shows the setup checklist instead of attention items when no folder is set", () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    seedProcessingQueries(qc);
    qc.setQueryData(processingLibrariesKey, [
      library({ id: 1, name: "Movies" }),
      library({ id: 2, name: "TV", media_type: "tv" }),
    ]);
    qc.setQueryData(qk.me, operatorMe);
    render(wrap(<ProcessingPage />, qc));
    expect(screen.getByTestId("processing-guided-setup")).toHaveTextContent(
      "Get started",
    );
    expect(
      screen.queryByTestId("processing-overview-needs-attention"),
    ).toBeNull();
    const names = screen
      .getAllByTestId("processing-overview-library")
      .map((row) => row.querySelector("th")?.textContent);
    expect(names).toEqual(["Movies", "TV"]);
  });

  it("Jobs tab shows jobs inspection with honest split from Activity", () => {
    renderProcessingPage();
    openTab("Jobs");
    const block = screen.getByTestId("processing-jobs-inspection-section");
    expect(block.textContent).toMatch(/Activity/i);
    expect(block.textContent).toMatch(/Current and recent work/i);
    expect(block.textContent).toMatch(/clear next step/i);
  });

  it("Libraries tab shows processing settings controls", () => {
    renderProcessingPage();
    openTab("Libraries");
    const section = screen.getByText("Processing, safety and records");
    expect(section).toBeInTheDocument();
  });

  it("Libraries tab exposes process controls for concurrency and file-age guardrail", () => {
    renderProcessingPage();
    openTab("Libraries");
    const block = screen
      .getByText("Processing, safety and records")
      .closest("section");
    expect(block).not.toBeNull();
    const text = block?.textContent ?? "";
    expect(text).toMatch(/Absolute file limit/i);
    expect(text).toMatch(/Minimum unchanged age/i);
    expect(text).toMatch(/Verbose file-detection records/i);
  });

  it("top-level tabs no longer include Workers", () => {
    renderProcessingPage();
    expect(screen.queryByRole("tab", { name: "Workers" })).toBeNull();
  });

  it("top-level tabs no longer include Operations", () => {
    renderProcessingPage();
    expect(screen.queryByRole("tab", { name: "Operations" })).toBeNull();
  });

  it("top-level tabs include Schedules", () => {
    renderProcessingPage();
    expect(screen.getByRole("tab", { name: "Schedules" })).toBeInTheDocument();
  });

  it("lists Jobs tab after Schedules", () => {
    renderProcessingPage();
    const tabs = screen.getAllByRole("tab");
    const labels = tabs.map((t) => t.textContent?.trim() ?? "");
    const idxSched = labels.indexOf("Schedules");
    const idxJobs = labels.indexOf("Jobs");
    expect(idxSched).toBeGreaterThan(-1);
    expect(idxJobs).toBeGreaterThan(-1);
    expect(idxJobs).toBeGreaterThan(idxSched);
  });

  it("Schedules offers a scan-now action for each library", () => {
    renderProcessingPage();
    openTab("Schedules");
    const cards = screen.getAllByTestId("processing-schedules-library-scan");
    expect(cards).toHaveLength(3);
    expect(
      within(cards[0]).getByRole("button", { name: "Scan Films now" }),
    ).toBeEnabled();
    // A library with no watched folder has nothing to scan yet.
    expect(
      within(cards[1]).getByRole("button", { name: "Scan 4K films now" }),
    ).toBeDisabled();
    expect(
      within(cards[2]).getByRole("button", { name: "Scan Shows now" }),
    ).toBeDisabled();
  });

  it("Scan now queues a scan of that one library", async () => {
    const enqueue = vi
      .spyOn(scanApi, "postProcessingWatchedFolderRemuxScanDispatchEnqueue")
      .mockResolvedValue({
        ok: true,
        job_id: 41,
        dedupe_key: "scan",
        job_kind: "processing.watched_folder.remux_scan_dispatch.v1",
      });
    renderProcessingPage();
    openTab("Schedules");
    fireEvent.click(screen.getByRole("button", { name: "Scan Films now" }));

    await waitFor(() => {
      expect(enqueue).toHaveBeenCalledWith({
        enqueue_remux_jobs: true,
        media_scope: "movie",
        library_id: 1,
      });
    });
    expect(
      await screen.findByText("Queued scan job #41 for Films."),
    ).toBeInTheDocument();
    enqueue.mockRestore();
  });

  it("Schedules tab has no master scheduled-processing toggle (folder poll is under Libraries)", () => {
    renderProcessingPage();
    openTab("Schedules");
    expect(screen.queryByText("Enable scheduled processing")).toBeNull();
  });

  it("Schedules tab has no suite timezone preamble banner", () => {
    renderProcessingPage();
    openTab("Schedules");
    expect(
      screen.queryByText("Suite time zone for schedule windows"),
    ).toBeNull();
  });
});
