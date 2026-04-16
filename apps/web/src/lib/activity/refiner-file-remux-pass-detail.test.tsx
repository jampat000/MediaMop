import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RefinerFileRemuxPassActivityDetail } from "./refiner-file-remux-pass-detail";

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
    expect(screen.getByText(/Live — remux wrote an output file/i)).toBeInTheDocument();
    expect(screen.getByText("movies/a.mkv")).toBeInTheDocument();
    expect(screen.getByText("A before")).toBeInTheDocument();
    expect(screen.getByText(/ffmpeg command line/i)).toBeInTheDocument();
  });

  it("falls back to raw string when detail is not JSON", () => {
    render(<RefinerFileRemuxPassActivityDetail detail="not-json" />);
    expect(screen.getByTestId("refiner-remux-activity-detail-raw")).toHaveTextContent("not-json");
  });
});
