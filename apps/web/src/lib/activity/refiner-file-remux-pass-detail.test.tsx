import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RefinerFileProcessingProgressDetail, RefinerFileRemuxPassActivityDetail } from "./refiner-file-remux-pass-detail";

describe("RefinerFileRemuxPassActivityDetail", () => {
  it("renders structured remux fields from JSON detail", () => {
    const detail = JSON.stringify({
      outcome: "live_output_written",
      ok: true,
      relative_media_path: "movies/a.mkv",
      inspected_source_path: "/data/movies/a.mkv",
      stream_counts: { video: 1, audio: 2, subtitle: 0 },
      plan_summary: "video copy indices: [0] | audio out: #1 eng",
      audio_before: "A before",
      audio_after: "A after",
      subs_before: "S before",
      subs_after: "S after",
      after_track_lines_meaning: "Planned only.",
      remux_required: true,
      ffmpeg_argv: ["/bin/ffmpeg", "-i", "a.mkv", "out.mkv"],
    });
    render(<RefinerFileRemuxPassActivityDetail detail={detail} />);
    expect(screen.getByTestId("refiner-remux-activity-detail")).toBeInTheDocument();
    expect(screen.getByText("Outcome")).toBeInTheDocument();
    expect(screen.getByText("File processed")).toBeInTheDocument();
    expect(screen.getByText("Show track and cleanup details")).toBeInTheDocument();
    expect(screen.getByText("/data/movies/a.mkv")).toBeInTheDocument();
    expect(screen.getByText("Audio in file")).toBeInTheDocument();
    expect(screen.getByText("A before")).toBeInTheDocument();
    expect(screen.getByText(/ffmpeg command line/i)).toBeInTheDocument();
  });

  it("falls back to raw string when detail is not JSON", () => {
    render(<RefinerFileRemuxPassActivityDetail detail="not-json" />);
    expect(screen.getByTestId("refiner-remux-activity-detail-raw")).toHaveTextContent("not-json");
  });

  it("renders live Refiner processing progress in plain language", () => {
    const detail = JSON.stringify({
      status: "processing",
      relative_media_path: "movies/Caddyshack.mkv",
      percent: 42.4,
      eta_seconds: 71,
      elapsed_seconds: 50,
      processed_seconds: 1200,
      duration_seconds: 2800,
      speed: "16x",
      message: "Refiner is writing the cleaned-up file.",
    });
    render(<RefinerFileProcessingProgressDetail detail={detail} />);
    expect(screen.getByTestId("refiner-processing-progress-detail")).toBeInTheDocument();
    expect(screen.getByText("Processing")).toBeInTheDocument();
    expect(screen.getByText("42%")).toBeInTheDocument();
    expect(screen.getByText(/About 1m 11s left/i)).toBeInTheDocument();
    expect(screen.getByText(/Speed 16x/i)).toBeInTheDocument();
  });
});
