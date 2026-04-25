/** Persisted ``event_type`` for Refiner file remux pass must match backend ``REFINER_FILE_REMUX_PASS_COMPLETED``. */
export const REFINER_FILE_REMUX_PASS_COMPLETED_EVENT = "refiner.file_remux_pass_completed";
export const REFINER_FILE_PROCESSING_PROGRESS_EVENT = "refiner.file_processing_progress";

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
  removed_audio?: string[];
  removed_subtitles?: string[];
  after_track_lines_meaning?: string;
  remux_required?: boolean;
  live_mutations_skipped?: boolean;
  output_file?: string;
  reason?: string;
  job_id?: number;
  ffmpeg_argv?: string[];
  ffmpeg_argv_truncated?: boolean;
  source_size_bytes?: number | null;
  output_size_bytes?: number | null;
  output_completeness_note?: string | null;
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

type RefinerProgressDetail = {
  status?: string;
  message?: string;
  relative_media_path?: string;
  inspected_source_path?: string;
  output_file?: string;
  percent?: number | null;
  eta_seconds?: number | null;
  elapsed_seconds?: number | null;
  processed_seconds?: number | null;
  duration_seconds?: number | null;
  speed?: string | null;
  reason?: string | null;
};

function outcomeLabel(outcome: string | undefined): string {
  switch (outcome) {
    case "live_output_written":
      return "File processed";
    case "live_skipped_not_required":
      return "No changes needed";
    case "failed_before_execution":
      return "Could not check file";
    case "failed_during_execution":
      return "Could not process file";
    default:
      return outcome || "Unknown outcome";
  }
}

function formatBytes(value: number | null | undefined): string | null {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return null;
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  const decimals = size >= 100 || unitIndex === 0 ? 0 : size >= 10 ? 1 : 2;
  return `${size.toFixed(decimals)} ${units[unitIndex]}`;
}

function formatDuration(seconds: number | null | undefined): string | null {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds < 0) return null;
  const rounded = Math.round(seconds);
  const mins = Math.floor(rounded / 60);
  const secs = rounded % 60;
  if (mins <= 0) return `${secs}s`;
  const hours = Math.floor(mins / 60);
  const remMins = mins % 60;
  if (hours <= 0) return `${mins}m ${secs.toString().padStart(2, "0")}s`;
  return `${hours}h ${remMins.toString().padStart(2, "0")}m`;
}

function filenameFromPath(path: string | undefined): string {
  if (!path) return "this file";
  return path.split(/[\\/]/).filter(Boolean).at(-1) || "this file";
}

function formatSavings(source: number | null | undefined, output: number | null | undefined): string | null {
  if (typeof source !== "number" || typeof output !== "number" || !Number.isFinite(source) || !Number.isFinite(output)) {
    return null;
  }
  const delta = source - output;
  if (delta === 0) return "No size change";
  const percent = source > 0 ? Math.abs(delta / source) * 100 : null;
  const sizeText = formatBytes(Math.abs(delta));
  if (!sizeText) return null;
  if (percent != null && (percent < 0.1 || Math.abs(delta) < 1024 * 1024)) {
    const direction = delta > 0 ? "saved" : "container overhead";
    return `Size basically unchanged (${sizeText} ${direction})`;
  }
  if (delta > 0) {
    return percent != null ? `Saved ${sizeText} (${percent.toFixed(1)}%)` : `Saved ${sizeText}`;
  }
  return percent != null ? `Grew by ${sizeText} (${percent.toFixed(1)}%)` : `Grew by ${sizeText}`;
}

function cleanupStatus(parsed: RemuxDetail): { label: string; value: string }[] {
  if (parsed.media_scope === "movie") {
    return [
      {
        label: "Watched-folder cleanup",
        value: parsed.source_folder_deleted ? "Removed source release folder" : parsed.source_folder_skip_reason || "Not removed",
      },
      {
        label: "Output-folder cleanup",
        value:
          parsed.movie_output_folder_deleted
            ? "Removed output title folder"
            : parsed.movie_output_folder_skip_reason ||
              (parsed.movie_output_truth_check ? `Not removed (${parsed.movie_output_truth_check})` : "Not removed"),
      },
    ];
  }
  if (parsed.media_scope === "tv") {
    return [
      {
        label: "Watched-folder cleanup",
        value:
          parsed.tv_season_folder_deleted ? "Removed watched season folder" : parsed.tv_season_folder_skip_reason || "Not removed",
      },
      {
        label: "Output-folder cleanup",
        value:
          parsed.tv_output_season_folder_deleted
            ? "Removed output season folder"
            : parsed.tv_output_season_folder_skip_reason ||
              (parsed.tv_output_truth_check ? `Not removed (${parsed.tv_output_truth_check})` : "Not removed"),
      },
    ];
  }
  return [];
}

function detailRow(label: string, value: string | undefined | null) {
  if (value === undefined || value === null || value === "") return null;
  return (
    <div key={label} className="mm-activity-remux-detail__row">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function splitTrackList(value: string | undefined): string[] {
  if (!value) return [];
  return value
    .split(/[;,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function trackSection(label: string, values: string[], tone: "before" | "kept" | "removed", emptyLabel = "None") {
  if (values.length === 0) {
    return (
      <div key={label} className="mm-activity-remux-detail__tracks-section">
        <h5 className="mm-activity-remux-detail__tracks-title">{label}</h5>
        <p className="mm-activity-remux-detail__tracks-empty">{emptyLabel}</p>
      </div>
    );
  }

  return (
    <div key={label} className="mm-activity-remux-detail__tracks-section">
      <h5 className="mm-activity-remux-detail__tracks-title">{label}</h5>
      <div className="mm-activity-remux-detail__chips">
        {values.map((value) => (
          <span key={`${label}-${value}`} className={`mm-activity-remux-detail__chip mm-activity-remux-detail__chip--${tone}`}>
            {value}
          </span>
        ))}
      </div>
    </div>
  );
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

  const sourceSize = formatBytes(parsed.source_size_bytes);
  const outputSize = formatBytes(parsed.output_size_bytes);
  const savings = formatSavings(parsed.source_size_bytes, parsed.output_size_bytes);
  const cleanupRows = cleanupStatus(parsed);
  const streamsInspected = parsed.stream_counts
    ? `Video ${parsed.stream_counts.video ?? 0}, audio ${parsed.stream_counts.audio ?? 0}, subtitles ${parsed.stream_counts.subtitle ?? 0}`
    : undefined;
  const audioBeforeTracks = splitTrackList(parsed.audio_before);
  const audioAfterTracks = splitTrackList(parsed.audio_after);
  const subtitleBeforeTracks = splitTrackList(parsed.subs_before);
  const subtitleAfterTracks = splitTrackList(parsed.subs_after);
  const removedAudioTracks = parsed.removed_audio ?? [];
  const removedSubtitleTracks = parsed.removed_subtitles ?? [];

  const summaryTiles = [
    { label: "Outcome", value: outcomeLabel(parsed.outcome) },
    { label: "Original size", value: sourceSize },
    { label: "Final size", value: outputSize },
    { label: "Change", value: savings },
  ].filter((row) => row.value);

  const beforeRows = [
    detailRow("File checked", parsed.inspected_source_path || parsed.relative_media_path),
    detailRow("Original size", sourceSize),
    detailRow("Streams inspected", streamsInspected),
  ].filter(Boolean);

  const afterRows = [
    detailRow("Output file", parsed.output_file),
    detailRow("Final size", outputSize),
  ].filter(Boolean);

  const supplementalRows: { k: string; v: string | undefined | null }[] = [
    { k: "Changes needed", v: parsed.remux_required === undefined ? undefined : parsed.remux_required ? "Yes" : "No" },
    { k: "What Refiner planned", v: parsed.plan_summary },
    ...cleanupRows.map((row) => ({ k: row.label, v: row.value })),
    { k: "Safety note", v: parsed.output_completeness_note || undefined },
    { k: "Reason", v: parsed.reason },
  ];

  return (
    <div className="mm-activity-remux-detail" data-testid="refiner-remux-activity-detail">
      {summaryTiles.length > 0 ? (
        <div className="mm-activity-remux-detail__tiles">
          {summaryTiles.map((tile) => (
            <div key={tile.label} className="mm-activity-remux-detail__tile">
              <span className="mm-activity-remux-detail__tile-label">{tile.label}</span>
              <span className="mm-activity-remux-detail__tile-value">{tile.value}</span>
            </div>
          ))}
        </div>
      ) : null}
      <details className="mm-activity-remux-detail__expand">
        <summary>Show track and cleanup details</summary>
        <div className="mm-activity-remux-detail__expand-body">
          <div className="mm-activity-remux-detail__compare">
            <section className="mm-activity-remux-detail__column">
              <h4 className="mm-activity-remux-detail__column-title">Before</h4>
              <dl className="mm-activity-remux-detail__dl">{beforeRows}</dl>
              <div className="mm-activity-remux-detail__tracks">
                {trackSection("Audio in file", audioBeforeTracks, "before")}
                {trackSection("Subtitles in file", subtitleBeforeTracks, "before")}
              </div>
            </section>
            <section className="mm-activity-remux-detail__column">
              <h4 className="mm-activity-remux-detail__column-title">After</h4>
              <dl className="mm-activity-remux-detail__dl">{afterRows}</dl>
              <div className="mm-activity-remux-detail__tracks">
                {trackSection("Audio kept", audioAfterTracks, "kept")}
                {trackSection("Audio removed", removedAudioTracks, "removed", "None removed")}
                {trackSection("Subtitles kept", subtitleAfterTracks, "kept")}
                {trackSection("Subtitles removed", removedSubtitleTracks, "removed", "None removed")}
              </div>
            </section>
          </div>

          <div className="mm-activity-remux-detail__supplemental">
            <h4 className="mm-activity-remux-detail__section-title">Processing notes</h4>
            <dl className="mm-activity-remux-detail__dl">
              {supplementalRows
                .filter((r) => r.v !== undefined && r.v !== null && r.v !== "")
                .map((r) => (
                  <div key={r.k} className="mm-activity-remux-detail__row">
                    <dt>{r.k}</dt>
                    <dd>{String(r.v)}</dd>
                  </div>
                ))}
            </dl>
          </div>

          {Array.isArray(parsed.ffmpeg_argv) && parsed.ffmpeg_argv.length > 0 ? (
            <details className="mm-activity-remux-detail__ffmpeg">
              <summary>
                ffmpeg command line
                {parsed.ffmpeg_argv_truncated ? " (truncated in log)" : ""}
              </summary>
              <pre className="mm-activity-remux-detail__pre">{parsed.ffmpeg_argv.join(" ")}</pre>
            </details>
          ) : null}
        </div>
      </details>
    </div>
  );
}

export function RefinerFileProcessingProgressDetail({ detail }: { detail: string }) {
  let parsed: RefinerProgressDetail | null = null;
  try {
    const raw: unknown = JSON.parse(detail);
    parsed = typeof raw === "object" && raw !== null ? (raw as RefinerProgressDetail) : null;
  } catch {
    parsed = null;
  }

  if (!parsed) {
    return <p className="text-sm leading-6 text-[var(--mm-text2)]">{detail}</p>;
  }

  const rawPercent = typeof parsed.percent === "number" && Number.isFinite(parsed.percent) ? parsed.percent : null;
  const percent = rawPercent == null ? null : Math.max(0, Math.min(100, rawPercent));
  const status = parsed.status || "processing";
  const fileName = filenameFromPath(parsed.relative_media_path || parsed.inspected_source_path);
  const eta = formatDuration(parsed.eta_seconds);
  const elapsed = formatDuration(parsed.elapsed_seconds);
  const processed = formatDuration(parsed.processed_seconds);
  const duration = formatDuration(parsed.duration_seconds);
  const statusText =
    status === "finished"
      ? "Finished"
      : status === "failed"
        ? "Stopped"
        : status === "finishing"
          ? "Final checks"
          : "Processing";

  return (
    <div className="mm-activity-processing" data-testid="refiner-processing-progress-detail">
      <div className="mm-activity-processing__header">
        <div>
          <p className="mm-activity-processing__eyebrow">{statusText}</p>
          <p className="mm-activity-processing__title">{parsed.message || `Refiner is processing ${fileName}.`}</p>
        </div>
        <strong className="mm-activity-processing__percent">{percent == null ? "Working" : `${Math.round(percent)}%`}</strong>
      </div>
      <div className="mm-activity-processing__bar" aria-label={`Processing progress for ${fileName}`}>
        <span style={{ width: `${percent ?? 8}%` }} />
      </div>
      <div className="mm-activity-processing__metrics">
        <span>{eta ? `About ${eta} left` : status === "processing" ? "Estimating time left" : statusText}</span>
        {elapsed ? <span>Running {elapsed}</span> : null}
        {processed && duration ? <span>Processed {processed} of {duration}</span> : null}
        {parsed.speed ? <span>Speed {parsed.speed}</span> : null}
      </div>
      {parsed.reason ? <p className="mm-activity-processing__error">{parsed.reason}</p> : null}
    </div>
  );
}
