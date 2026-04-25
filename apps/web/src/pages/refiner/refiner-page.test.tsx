import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { UserPublic } from "../../lib/api/types";
import { qk } from "../../lib/auth/queries";
import { refinerJobsInspectionQueryKey } from "../../lib/refiner/jobs-inspection/queries";
import {
  refinerOperatorSettingsQueryKey,
  refinerOverviewStatsQueryKey,
  refinerPathSettingsQueryKey,
  refinerRemuxRulesSettingsQueryKey,
} from "../../lib/refiner/queries";
import type { RefinerPathSettingsOut, RefinerRemuxRulesSettingsOut } from "../../lib/refiner/types";
import { RefinerPage } from "./refiner-page";

const operatorMe: UserPublic = { id: 1, username: "alice", role: "operator" };

/** Seeded path API shape: default work folders live under MediaMop runtime data. */
const minimalRefinerPathSettings: RefinerPathSettingsOut = {
  refiner_watched_folder: null,
  refiner_watched_folder_exists: false,
  refiner_work_folder: null,
  refiner_output_folder: "",
  resolved_default_work_folder: "C:\\ProgramData\\MediaMop\\refiner\\refiner-movie-work",
  effective_work_folder: "C:\\ProgramData\\MediaMop\\refiner\\refiner-movie-work",
  refiner_tv_watched_folder: null,
  refiner_tv_watched_folder_exists: false,
  refiner_tv_work_folder: null,
  refiner_tv_output_folder: null,
  resolved_default_tv_work_folder: "C:\\ProgramData\\MediaMop\\refiner\\refiner-tv-work",
  effective_tv_work_folder: "C:\\ProgramData\\MediaMop\\refiner\\refiner-tv-work",
  movie_watched_folder_check_interval_seconds: 300,
  tv_watched_folder_check_interval_seconds: 300,
  updated_at: "2026-04-11T00:00:00Z",
};

const minimalRefinerRemuxRules: RefinerRemuxRulesSettingsOut = {
  movie: {
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
  },
  tv: {
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
  },
  updated_at: "2026-04-11T00:00:00Z",
};

function wrap(ui: ReactNode, client: QueryClient) {
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

function seedRefinerQueries(qc: QueryClient) {
  qc.setQueryData(refinerOverviewStatsQueryKey, {
    window_days: 30,
    files_processed: 42,
    files_failed: 1,
    success_rate_percent: 97.7,
  });
  qc.setQueryData(refinerPathSettingsQueryKey, minimalRefinerPathSettings);
  qc.setQueryData(refinerOperatorSettingsQueryKey, {
    max_concurrent_files: 1,
    min_file_age_seconds: 60,
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
  qc.setQueryData(refinerRemuxRulesSettingsQueryKey, minimalRefinerRemuxRules);
  qc.setQueryData(refinerJobsInspectionQueryKey("recent"), { jobs: [], default_recent_slice: true });
  qc.setQueryData(refinerJobsInspectionQueryKey("pending"), { jobs: [] });
  qc.setQueryData(refinerJobsInspectionQueryKey("leased"), { jobs: [] });
  qc.setQueryData(refinerJobsInspectionQueryKey("failed"), { jobs: [] });
}

function openTab(label: string) {
  fireEvent.click(screen.getByRole("tab", { name: label }));
}

function renderRefinerPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  seedRefinerQueries(qc);
  qc.setQueryData(qk.me, operatorMe);
  return render(wrap(<RefinerPage />, qc));
}

describe("RefinerPage", () => {
  it("renders the Refiner shell", () => {
    renderRefinerPage();
    expect(screen.getByTestId("refiner-scope-page")).toBeInTheDocument();
  });

  it("Overview is the default tab, stays Refiner-scoped, and links Activity without leaking env keys", () => {
    renderRefinerPage();
    expect(screen.getByTestId("refiner-overview-panel")).toBeInTheDocument();
    const overview = screen.getByTestId("refiner-overview-panel").textContent ?? "";
    expect(overview).toMatch(/At a glance/i);
    expect(overview).not.toMatch(/MEDIAMOP_/i);
    expect(overview).not.toMatch(/refiner_jobs/i);
    expect(screen.getByRole("link", { name: "Activity" })).toHaveAttribute("href", "/app/activity");
  });

  it("Overview surfaces saved audio/subtitle defaults at a glance", () => {
    renderRefinerPage();
    const card = screen.getByTestId("refiner-overview-audio-subtitles-glance");
    expect(card.textContent).toMatch(/Audio & subtitles/i);
    expect(card.textContent).toMatch(/English/i);
    expect(card.textContent).toMatch(/Japanese/i);
    expect(card.textContent).toMatch(/Remove all subtitles/i);
  });

  it("Overview shows last-30-day stats card", () => {
    renderRefinerPage();
    const panel = screen.getByTestId("refiner-overview-at-a-glance");
    const last30 = screen.getByTestId("refiner-overview-last-30-days");
    expect(panel.textContent).toMatch(/Last 30 days/i);
    expect(last30.textContent).toMatch(/Completed/i);
    expect(last30.textContent).toMatch(/42/);
    expect(last30.textContent).toMatch(/Failed/i);
    expect(last30.textContent).toMatch(/Success/i);
    expect(last30.textContent).toMatch(/97.7%/);
    expect(panel.textContent).toMatch(/Throughput & safety/i);
  });

  it("Jobs tab shows Refiner jobs inspection with honest split from Activity", () => {
    renderRefinerPage();
    openTab("Jobs");
    const block = screen.getByTestId("refiner-jobs-inspection-section");
    expect(block.textContent).toMatch(/Activity/i);
    expect(block.textContent).toMatch(/Pending, running, and recent Refiner work/i);
  });

  it("Libraries tab shows processing settings controls", () => {
    renderRefinerPage();
    openTab("Libraries");
    const section = screen.getByText("Processing settings");
    expect(section).toBeInTheDocument();
  });

  it("Libraries tab exposes process controls for concurrency and file-age guardrail", () => {
    renderRefinerPage();
    openTab("Libraries");
    const block = screen.getByText("Processing settings").closest("section");
    expect(block).not.toBeNull();
    const text = block?.textContent ?? "";
    expect(text).toMatch(/Files at once/i);
    expect(text).toMatch(/Minimum file age/i);
  });

  it("top-level tabs no longer include Workers", () => {
    renderRefinerPage();
    expect(screen.queryByRole("tab", { name: "Workers" })).toBeNull();
  });

  it("top-level tabs no longer include Operations", () => {
    renderRefinerPage();
    expect(screen.queryByRole("tab", { name: "Operations" })).toBeNull();
  });

  it("top-level tabs include Schedules", () => {
    renderRefinerPage();
    expect(screen.getByRole("tab", { name: "Schedules" })).toBeInTheDocument();
  });

  it("lists Jobs tab after Schedules", () => {
    renderRefinerPage();
    const tabs = screen.getAllByRole("tab");
    const labels = tabs.map((t) => t.textContent?.trim() ?? "");
    const idxSched = labels.indexOf("Schedules");
    const idxJobs = labels.indexOf("Jobs");
    expect(idxSched).toBeGreaterThan(-1);
    expect(idxJobs).toBeGreaterThan(-1);
    expect(idxJobs).toBeGreaterThan(idxSched);
  });

  it("Schedules includes independent TV and Movies scan-now actions", () => {
    renderRefinerPage();
    openTab("Schedules");
    expect(screen.getByRole("button", { name: "Scan TV now" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Scan Movies now" })).toBeInTheDocument();
  });

  it("Schedules tab has no master scheduled-processing toggle (folder poll is under Libraries)", () => {
    renderRefinerPage();
    openTab("Schedules");
    expect(screen.queryByText("Enable scheduled processing")).toBeNull();
  });

  it("Schedules tab has no suite timezone preamble banner", () => {
    renderRefinerPage();
    openTab("Schedules");
    expect(screen.queryByText("Suite time zone for schedule windows")).toBeNull();
  });
});
