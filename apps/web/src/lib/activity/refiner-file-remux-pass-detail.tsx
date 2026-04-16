/** Persisted ``event_type`` for Refiner file remux pass — must match backend ``REFINER_FILE_REMUX_PASS_COMPLETED``. */
export const REFINER_FILE_REMUX_PASS_COMPLETED_EVENT = "refiner.file_remux_pass_completed";

type RemuxDetail = {
  outcome?: string;
  ok?: boolean;
  media_scope?: string;
  relative_media_path?: string;
  inspected_source_path?: string;
  stream_counts?: { video?: number; audio?: number; subtitle?: number };
  plan_summary?: string;
  audio_before?: string;
  audio_after?: string;
  subs_before?: string;
  subs_after?: string;
  after_track_lines_meaning?: string;
  remux_required?: boolean;
  live_mutations_skipped?: boolean;
  output_file?: string;
  reason?: string;
  job_id?: number;
  ffmpeg_argv_truncated?: boolean;
  source_folder_deleted?: boolean;
  source_folder_skip_reason?: string;
  tv_season_folder_deleted?: boolean;
  tv_season_folder_skip_reason?: string;
  movie_output_folder_deleted?: boolean;
  movie_output_folder_skip_reason?: string;
  movie_output_truth_check?: string;
  tv_output_season_folder_deleted?: boolean;
  tv_output_season_folder_skip_reason?: string;
  tv_output_truth_check?: string;
};

function outcomeLabel(outcome: string | undefined): string {
  switch (outcome) {
    case "live_output_written":
      return "Live — remux wrote an output file";
    case "live_skipped_not_required":
      return "Live — skipped ffmpeg (file already matched the plan)";
    case "failed_before_execution":
      return "Failed before ffmpeg (probe, plan, or validation)";
    case "failed_during_execution":
      return "Failed during ffmpeg or output validation";
    default:
      return outcome || "Unknown outcome";
  }
}

export function RefinerFileRemuxPassActivityDetail({ detail }: { detail: string }) {
  let parsed: RemuxDetail | null = null;
  try {
    const raw: unknown = JSON.parse(detail);
    parsed = typeof raw === "object" && raw !== null ? (raw as RemuxDetail) : null;
  } catch {
    parsed = null;
  }

  if (!parsed) {
    return (
      <span
        className="mm-activity-row__detail mm-activity-row__detail--raw"
        data-testid="refiner-remux-activity-detail-raw"
      >
        {detail}
      </span>
    );
  }

  const rows: { k: string; v: string | undefined | null | false | 0 }[] = [
    { k: "Outcome", v: outcomeLabel(parsed.outcome) },
    { k: "Scope", v: parsed.media_scope },
    { k: "Relative path", v: parsed.relative_media_path },
    { k: "Inspected file", v: parsed.inspected_source_path },
  ];
  if (parsed.stream_counts) {
    const c = parsed.stream_counts;
    rows.push({
      k: "Streams inspected",
      v: `video ${c.video ?? 0}, audio ${c.audio ?? 0}, subtitle ${c.subtitle ?? 0}`,
    });
  }
  rows.push(
    { k: "Remux required", v: parsed.remux_required === undefined ? "—" : parsed.remux_required ? "yes" : "no" },
    { k: "Plan summary", v: parsed.plan_summary },
    { k: "Audio (before)", v: parsed.audio_before },
    { k: "Audio (after selection)", v: parsed.audio_after },
    { k: "Subtitles (before)", v: parsed.subs_before },
    { k: "Subtitles (after selection)", v: parsed.subs_after },
    { k: "How to read the “after” lines", v: parsed.after_track_lines_meaning },
    { k: "Output file", v: parsed.output_file },
    { k: "Note / error", v: parsed.reason },
  );

  if (parsed.media_scope === "movie") {
    rows.push(
      {
        k: "Movies watched-folder cleanup",
        v: parsed.source_folder_deleted
          ? "removed source release folder"
          : parsed.source_folder_skip_reason || "not removed",
      },
      {
        k: "Movies output-folder cleanup",
        v: parsed.movie_output_folder_deleted
          ? "removed output title folder"
          : parsed.movie_output_folder_skip_reason ||
            (parsed.movie_output_truth_check ? `not removed (${parsed.movie_output_truth_check})` : undefined),
      },
    );
  } else if (parsed.media_scope === "tv") {
    rows.push(
      {
        k: "TV watched-folder cleanup",
        v: parsed.tv_season_folder_deleted
          ? "removed watched season folder"
          : parsed.tv_season_folder_skip_reason || "not removed",
      },
      {
        k: "TV output-folder cleanup",
        v: parsed.tv_output_season_folder_deleted
          ? "removed output season folder"
          : parsed.tv_output_season_folder_skip_reason ||
            (parsed.tv_output_truth_check ? `not removed (${parsed.tv_output_truth_check})` : undefined),
      },
    );
  }

  const argv = (parsed as { ffmpeg_argv?: string[] }).ffmpeg_argv;

  return (
    <div className="mm-activity-remux-detail" data-testid="refiner-remux-activity-detail">
      <dl className="mm-activity-remux-detail__dl">
        {rows
          .filter((r) => r.v !== undefined && r.v !== null && r.v !== "")
          .map((r) => (
            <div key={r.k} className="mm-activity-remux-detail__row">
              <dt>{r.k}</dt>
              <dd>{String(r.v)}</dd>
            </div>
          ))}
      </dl>
      {Array.isArray(argv) && argv.length > 0 ? (
        <details className="mm-activity-remux-detail__ffmpeg">
          <summary>
            ffmpeg command line
            {parsed.ffmpeg_argv_truncated ? " (truncated in log)" : ""}
          </summary>
          <pre className="mm-activity-remux-detail__pre">{argv.join(" ")}</pre>
        </details>
      ) : null}
    </div>
  );
}
