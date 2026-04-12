/** Persisted ``event_type`` for Refiner file remux pass — must match backend ``REFINER_FILE_REMUX_PASS_COMPLETED``. */
export const REFINER_FILE_REMUX_PASS_COMPLETED_EVENT = "refiner.file_remux_pass_completed";

type RemuxDetail = {
  outcome?: string;
  ok?: boolean;
  dry_run?: boolean;
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
};

function outcomeLabel(outcome: string | undefined): string {
  switch (outcome) {
    case "dry_run_planned":
      return "Dry run — planned only (no ffmpeg write, source unchanged)";
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
    { k: "Dry run", v: parsed.dry_run === undefined ? "—" : parsed.dry_run ? "yes" : "no" },
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
