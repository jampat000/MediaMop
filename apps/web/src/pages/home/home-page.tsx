/**
 * Home — what Weir is currently responsible for (#463). Until 3.0.0 this screen was
 * called "In hand"; the name changed, the subject did not.
 *
 * Weir is a stage in the middle of a pipeline. A media manager downloads a release into a
 * completed folder, Weir takes it, works on it, and writes it to an output folder the
 * manager then imports. It never sees the library on your storage, so this screen deliberately
 * never claims to: the subject is **custody**, not a library.
 *
 * It answers four questions, in this order:
 *   1. what arrived and is waiting
 *   2. what it is holding right now, and what is happening to each file
 *   3. what is stuck — and therefore missing from the manager
 *   4. what was handed back
 *
 * It is also the main screen, so it carries the few things the old dashboard did that
 * need a person (#459): no watched folder yet, workers that stopped, and jobs that failed.
 * Those appear only when they are true; a healthy install shows none of them.
 *
 * Laid out in the Weir content language — see docs/design/content-language.md. The lead band
 * is where the files Weir is holding are sitting right now, one segment per status, each as
 * wide as the number in it and each a filter into Files. The one figure row is today's
 * hand-back, which is question 4. Everything below is borderless.
 */

import { useCallback, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { DirectPlayLine } from "../../components/processing/direct-play-line";
import { FileStoryPanel } from "../../components/processing/file-story-panel";
import { Link } from "react-router-dom";
import { useActivityStreamInvalidations } from "../../lib/activity/use-activity-stream-invalidation";
import { PageLoading } from "../../components/shared/page-loading";
import { ApiEntryError } from "../../components/shared/api-entry-error";
import {
  PROCESSING_FILE_STATUS_LABELS,
  type ProcessingFile,
  type ProcessingFileStatus,
} from "../../lib/processing/files-api";
import {
  processingFilesKey,
  useProcessingFileLog,
  useProcessingFilesQuery,
} from "../../lib/processing/files-queries";
import {
  processingJobsInspectionQueryKey,
  useProcessingJobsInspectionQuery,
} from "../../lib/processing/jobs-inspection/queries";
import { useProcessingLibrariesQuery } from "../../lib/processing/libraries-queries";
import {
  processingOverviewStatsQueryKey,
  useProcessingOverviewStatsQuery,
} from "../../lib/processing/queries";
import { useSystemReadinessQuery } from "../../lib/system/readiness-queries";

/** Statuses that mean the file is Weir's responsibility right now. */
const HELD_STATUSES: ReadonlySet<string> = new Set([
  "unprocessed",
  "processing",
  "on_hold",
  "out_of_schedule",
  "blocked_upstream",
]);

/** Statuses that mean the manager will not see this file until somebody acts. */
const STUCK: ReadonlySet<string> = new Set(["processing_failed"]);

/**
 * The lead band: every place a file Weir is holding can be sitting, left to right, including
 * the one place it can be stuck. Together these are one whole — everything in Weir's hands —
 * so a segment's share of the band is honestly its share of the files. Each is a real file
 * status, so clicking it opens Files filtered to exactly that status.
 *
 * The labels are this screen's own words for custody, not the Files tab's status names:
 * "Arriving" rather than "Waiting", "Stuck" rather than "Failed".
 */
const HOLDING_STAGES: {
  status: ProcessingFileStatus;
  label: string;
  hint: string;
  live?: boolean;
}[] = [
  {
    status: "unprocessed",
    label: "Arriving",
    hint: "Handed over, not started",
  },
  {
    status: "processing",
    label: "Working",
    hint: "Being rewritten now",
    live: true,
  },
  { status: "on_hold", label: "On hold", hint: "Waiting for a free lane" },
  {
    status: "out_of_schedule",
    label: "Out of hours",
    hint: "Outside its library's window",
  },
  {
    status: "blocked_upstream",
    label: "Held upstream",
    hint: "Your manager still has it",
  },
  { status: "processing_failed", label: "Stuck", hint: "Needs a person" },
];

const FILES_QUERY = { limit: 200 } as const;
const FAILED_JOBS_LIMIT = 100;
// The screen moves as work does, so it follows the activity stream rather than a reload.
const LIVE_KEYS = [
  processingFilesKey(FILES_QUERY),
  [...processingOverviewStatsQueryKey, 1],
  processingJobsInspectionQueryKey("failed", FAILED_JOBS_LIMIT),
] as const;

/** One thing that is blocking or broken: a sentence and a way out, above the band. */
type Interrupt = {
  key: string;
  text: string;
  to: string;
  action: string;
};

function filesHref(status?: ProcessingFileStatus): string {
  return status
    ? `/processing?tab=files&status=${status}`
    : "/processing?tab=files";
}

function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = Math.abs(bytes);
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const shown =
    value >= 100 || unit === 0 ? Math.round(value) : value.toFixed(1);
  return `${bytes < 0 ? "-" : ""}${shown} ${units[unit]}`;
}

function formatEta(seconds: number | null): string | null {
  if (seconds === null || !Number.isFinite(seconds) || seconds <= 0)
    return null;
  if (seconds < 90) return `${Math.round(seconds)}s left`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 90) return `${minutes}m left`;
  return `${Math.round(minutes / 60)}h left`;
}

/** What the file is, from the probe. Nulls mean "not probed yet" and are simply omitted. */
function mediaFacts(file: ProcessingFile): string {
  const bits: string[] = [];
  if (file.video_codec) {
    bits.push(
      file.video_height
        ? `${file.video_codec} ${file.video_height}p`
        : file.video_codec,
    );
  } else if (file.video_height) {
    bits.push(`${file.video_height}p`);
  }
  if (file.audio_track_count !== null) {
    bits.push(
      file.audio_track_count === 1
        ? "1 audio track"
        : `${file.audio_track_count} audio tracks`,
    );
  }
  if (file.subtitle_track_count) {
    bits.push(
      file.subtitle_track_count === 1
        ? "1 subtitle"
        : `${file.subtitle_track_count} subtitles`,
    );
  }
  return bits.join(" · ");
}

function statusToneClass(status: string): string {
  if (STUCK.has(status)) return "mm-status-text--failed";
  if (status === "processing") return "mm-status-text--warning";
  if (status === "processed") return "mm-status-text--healthy";
  if (status === "blocked_upstream") return "mm-home-row__state--held";
  return "";
}

function FileRow({
  file,
  onOpen,
}: {
  file: ProcessingFile;
  onOpen: (file: ProcessingFile) => void;
}): React.ReactElement {
  const name = file.relative_path.split(/[\\/]/).pop() || file.relative_path;
  const facts = mediaFacts(file);
  const eta = formatEta(file.progress_eta_seconds);
  const percent = file.progress_percent;

  return (
    <li className="mm-home-row" data-testid="home-row">
      <div className="mm-home-row__main">
        <button
          type="button"
          className="mm-home-row__name"
          title={`What happened to ${file.relative_path}`}
          onClick={() => onOpen(file)}
        >
          {name}
        </button>
        <span className="mm-home-row__facts">
          {[formatBytes(file.size_bytes), facts].filter(Boolean).join(" · ")}
        </span>
        <DirectPlayLine
          directPlay={file.direct_play}
          testId={`home-direct-play-${file.id}`}
        />
      </div>

      <div className="mm-home-row__state">
        <span className={statusToneClass(file.status)}>
          {PROCESSING_FILE_STATUS_LABELS[file.status] ?? file.status}
          {file.blocked_by_connection
            ? ` — ${file.blocked_by_connection} is importing it`
            : ""}
        </span>
        {/* The reason sentence is written for the operator by the pass itself. */}
        {file.status_reason ? (
          <span className="mm-home-row__reason">{file.status_reason}</span>
        ) : null}
        {percent !== null ? (
          <span className="mm-home-row__progress">
            <span
              className="mm-home-row__progress-track"
              role="progressbar"
              aria-valuenow={Math.round(percent)}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={`Processing ${name}`}
            >
              <span
                className="mm-home-row__progress-fill"
                style={{ width: `${Math.max(2, Math.round(percent))}%` }}
              />
            </span>
            <span className="mm-home-row__progress-text">
              {Math.round(percent)}%{eta ? ` · ${eta}` : ""}
            </span>
          </span>
        ) : null}
      </div>
    </li>
  );
}

/** The band: where the files Weir is holding are sitting. In a row each stage is as wide as its
 *  count; below that the primitive restacks them into a labelled list by itself. */
function HoldingBand({
  counts,
}: {
  counts: Record<string, number>;
}): React.ReactElement {
  const stages = HOLDING_STAGES.map((stage) => ({
    ...stage,
    count: counts[stage.status] ?? 0,
  }));
  const total = stages.reduce((sum, stage) => sum + stage.count, 0);
  return (
    <div className="mm-lead-band" data-testid="home-band">
      {stages.map((stage) => {
        const live = Boolean(stage.live) && stage.count > 0;
        const modifier =
          stage.count === 0
            ? " mm-lead-band__segment--empty"
            : live
              ? " mm-lead-band__segment--live"
              : "";
        // Share of the band: the count itself, floored so an empty stage still reads
        // as a stage rather than vanishing.
        const share = total === 0 ? 1 : Math.max(stage.count, total * 0.06);
        return (
          <Link
            key={stage.status}
            className={`mm-lead-band__segment${modifier}`}
            style={{ "--mm-flow-share": share } as CSSProperties}
            to={filesHref(stage.status)}
            data-testid="home-band-stage"
          >
            <span className="mm-lead-band__label">
              {stage.label}
              {live ? (
                <i className="mm-lead-band__pulse" aria-hidden="true" />
              ) : null}
            </span>
            <span className="mm-lead-band__value">
              {stage.count.toLocaleString()}
            </span>
            <span className="mm-lead-band__hint">{stage.hint}</span>
            <span className="mm-lead-band__go" aria-hidden="true">
              Filter →
            </span>
          </Link>
        );
      })}
    </div>
  );
}

function QuietSection({
  headingId,
  heading,
  ariaLabel,
  aside,
  children,
}: {
  headingId?: string;
  heading: string;
  ariaLabel?: string;
  aside?: React.ReactNode;
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <section
      className="mm-quiet-section"
      aria-label={ariaLabel}
      aria-labelledby={ariaLabel ? undefined : headingId}
    >
      <div className="mm-quiet-section__head">
        <h2 id={headingId} className="mm-quiet-section__title">
          {heading}
        </h2>
        {aside ? <div className="mm-quiet-section__aside">{aside}</div> : null}
      </div>
      <div className="mm-quiet-section__body">{children}</div>
    </section>
  );
}

export function HomePage(): React.ReactElement {
  useActivityStreamInvalidations(LIVE_KEYS, { exact: true, throttleMs: 1_500 });
  const files = useProcessingFilesQuery(FILES_QUERY);
  const today = useProcessingOverviewStatsQuery(1);
  const libraries = useProcessingLibrariesQuery();
  const failedJobs = useProcessingJobsInspectionQuery(
    "failed",
    FAILED_JOBS_LIMIT,
  );
  const readiness = useSystemReadinessQuery();
  const fileLog = useProcessingFileLog();
  const [storyFile, setStoryFile] = useState<ProcessingFile | null>(null);

  const openStory = useCallback(
    (file: ProcessingFile) => {
      setStoryFile(file);
      fileLog.mutate(file.id);
    },
    [fileLog],
  );
  const closeStory = useCallback(() => setStoryFile(null), []);

  const grouped = useMemo(() => {
    const rows = (files.data?.files ?? []).filter((f) =>
      HELD_STATUSES.has(f.status),
    );
    const byLibrary = new Map<string, ProcessingFile[]>();
    for (const row of rows) {
      const key = row.library_name || "Unknown library";
      const list = byLibrary.get(key);
      if (list) list.push(row);
      else byLibrary.set(key, [row]);
    }
    // Working files first inside each library — they are what an operator looks for.
    for (const list of byLibrary.values()) {
      list.sort((a, b) => {
        const rank = (f: ProcessingFile) => (f.status === "processing" ? 0 : 1);
        return (
          rank(a) - rank(b) || a.relative_path.localeCompare(b.relative_path)
        );
      });
    }
    return [...byLibrary.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [files.data]);

  const stuck = useMemo(
    () => (files.data?.files ?? []).filter((f) => STUCK.has(f.status)),
    [files.data],
  );

  if (files.isPending) {
    return <PageLoading />;
  }
  if (files.isError) {
    return (
      <div className="mm-page">
        <ApiEntryError error={files.error} />
      </div>
    );
  }

  const counts = files.data?.status_counts ?? {};
  const working = counts.processing ?? 0;
  const heldTotal = [...HELD_STATUSES].reduce(
    (n, s) => n + (counts[s] ?? 0),
    0,
  );
  const holdingTotal = HOLDING_STAGES.reduce(
    (n, stage) => n + (counts[stage.status] ?? 0),
    0,
  );
  const watchedFolder = libraries.data?.[0]?.watched_folder ?? "";
  const outputFolder = libraries.data?.[0]?.output_folder ?? "";

  // Nothing to watch is the strongest empty on this page: it wins outright, and the band
  // and the figure row do not draw at all. A fresh install must never show a row of zeroes.
  const noWatchedFolder = Boolean(
    libraries.data &&
    !libraries.data.some((l) => l.enabled && l.watched_folder.trim()),
  );

  const interrupts: Interrupt[] = [];
  if (noWatchedFolder) {
    interrupts.push({
      key: "setup",
      text: "Nothing to watch yet. Weir picks files up from a library's watched folder — add one, or turn an existing library on.",
      to: "/processing?tab=libraries",
      action: "Set up a library",
    });
  }
  for (const worker of readiness.data?.worker_health ?? []) {
    if (worker.status !== "degraded") continue;
    interrupts.push({
      key: `worker-${worker.module}`,
      text: `Background work has stopped. ${worker.detail}`,
      to: "/processing?tab=jobs",
      action: "Open jobs",
    });
  }
  const failedJobCount = failedJobs.data?.jobs.length ?? 0;
  if (failedJobCount > 0) {
    const shown =
      failedJobCount >= FAILED_JOBS_LIMIT
        ? `${FAILED_JOBS_LIMIT}+`
        : String(failedJobCount);
    interrupts.push({
      key: "failed-jobs",
      text: `${failedJobCount === 1 ? "1 job failed" : `${shown} jobs failed`}. Each one says what went wrong and what to do next.`,
      to: "/processing?tab=jobs&status=failed",
      action: "Review failed jobs",
    });
  }
  if (stuck.length > 0) {
    interrupts.push({
      key: "stuck",
      text:
        stuck.length === 1
          ? "1 file is stuck in Weir's hands, so your media manager is still missing it."
          : `${stuck.length} files are stuck in Weir's hands, so your media manager is still missing them.`,
      to: filesHref("processing_failed"),
      action: "Open Files",
    });
  }

  const stats = today.data;

  return (
    <div className="mm-page">
      <header className="mm-page__intro">
        <p className="mm-page__eyebrow">
          Between your manager and your storage
        </p>
        <h1 className="mm-page__title">Home</h1>
        <p className="mm-page__lead">
          Files Weir is responsible for right now, between your media manager
          handing them over and getting them back.
        </p>
      </header>

      <div className="mm-quiet-stack">
        <div className="mm-lead">
          {interrupts.length > 0 ? (
            <ul className="mm-interrupt" data-testid="home-notices">
              {interrupts.map((item) => (
                <li key={item.key} className="mm-interrupt__item">
                  <span className="mm-interrupt__text">{item.text}</span>
                  <Link className="mm-quiet-link" to={item.to}>
                    {item.action} →
                  </Link>
                </li>
              ))}
            </ul>
          ) : null}

          {noWatchedFolder ? null : (
            <>
              {holdingTotal === 0 ? (
                <p className="mm-quiet-note" data-testid="home-band-empty">
                  Weir is holding nothing right now. Anything your manager drops
                  in a watched folder shows up here after the next scan.
                </p>
              ) : (
                <HoldingBand counts={counts} />
              )}

              <p className="mm-lead-caption" data-testid="home-caption">
                <span>
                  {holdingTotal === 0
                    ? "Weir picks a file up once your manager has finished writing it."
                    : "Open a stage to see the files sitting in it."}
                  {watchedFolder ? ` Files arrive in ${watchedFolder}.` : ""}
                </span>
                <span>
                  {working > 0
                    ? `${working.toLocaleString()} being worked on right now.`
                    : heldTotal > 0
                      ? `${heldTotal.toLocaleString()} waiting their turn.`
                      : "Nothing is waiting."}
                </span>
              </p>

              <div className="mm-figure-row" data-testid="home-today">
                <section className="mm-figure mm-figure--hero">
                  <div className="mm-figure__eyebrow">
                    <span>Handed back today</span>
                  </div>
                  <div className="mm-figure__value">
                    {stats ? stats.files_processed.toLocaleString() : "…"}
                    <span className="mm-figure__unit">
                      files back with your manager
                    </span>
                  </div>
                  <p className="mm-figure__note">
                    {outputFolder
                      ? `Written to ${outputFolder} for your manager to import.`
                      : "Written to each library's output folder for your manager to import."}
                  </p>
                  {stats ? (
                    <div className="mm-figure__foot">
                      <div>
                        <span className="mm-figure__foot-value">
                          {stats.output_written_count.toLocaleString()}
                        </span>
                        <span className="mm-figure__foot-label">Rewritten</span>
                      </div>
                      <div>
                        <span className="mm-figure__foot-value">
                          {stats.already_optimized_count.toLocaleString()}
                        </span>
                        <span className="mm-figure__foot-label">
                          Already right
                        </span>
                      </div>
                    </div>
                  ) : null}
                </section>

                <section className="mm-figure">
                  <div className="mm-figure__eyebrow">
                    <span>Reclaimed today</span>
                  </div>
                  <div className="mm-figure__value">
                    {stats ? formatBytes(stats.net_space_saved_bytes) : "…"}
                  </div>
                  {stats && stats.net_space_saved_percent > 0 ? (
                    <div
                      className="mm-figure__meter"
                      aria-hidden="true"
                      style={
                        {
                          "--mm-meter-fill": `${Math.min(100, stats.net_space_saved_percent)}%`,
                        } as CSSProperties
                      }
                    />
                  ) : null}
                  <p className="mm-figure__note">
                    {stats && stats.net_space_saved_percent > 0
                      ? `${stats.net_space_saved_percent}% smaller than what arrived`
                      : "Net space saved by the tracks Weir removed"}
                  </p>
                </section>

                <section
                  className={`mm-figure${
                    stats && stats.files_failed > 0 ? " mm-figure--warn" : ""
                  }`}
                >
                  <div className="mm-figure__eyebrow">
                    <span>Failed today</span>
                  </div>
                  <div className="mm-figure__value">
                    {stats ? stats.files_failed.toLocaleString() : "…"}
                  </div>
                  <p className="mm-figure__note">
                    {!stats
                      ? "Files Weir could not finish"
                      : stats.files_failed === 0
                        ? "Nothing failed today"
                        : "Weir could not finish these, and kept the originals"}
                  </p>
                </section>
              </div>
            </>
          )}
        </div>

        {stuck.length > 0 ? (
          <QuietSection
            headingId="home-stuck"
            heading="Stuck in Weir's hands"
            aside={
              <Link
                className="mm-quiet-link"
                to={filesHref("processing_failed")}
              >
                Open Files to deal with them →
              </Link>
            }
          >
            <p className="mm-quiet-note">
              Your media manager will not see these until they are dealt with.
              The originals are untouched in the watched folder.
            </p>
            <ul className="mm-home-list">
              {stuck.map((file) => (
                <FileRow key={file.id} file={file} onOpen={openStory} />
              ))}
            </ul>
          </QuietSection>
        ) : null}

        {grouped.length === 0 && stuck.length === 0 ? (
          <QuietSection headingId="home-empty" heading="Nothing held right now">
            <p className="mm-quiet-note">
              Every file your manager handed over has been dealt with and passed
              back. New arrivals in a watched folder will show up here.
            </p>
          </QuietSection>
        ) : (
          grouped.map(([libraryName, rows]) => (
            <QuietSection
              key={libraryName}
              heading={libraryName}
              ariaLabel={libraryName}
              aside={
                <p className="mm-quiet-note">
                  {rows.length === 1 ? "1 file" : `${rows.length} files`}
                </p>
              }
            >
              <ul className="mm-home-list">
                {rows.map((file) => (
                  <FileRow key={file.id} file={file} onOpen={openStory} />
                ))}
              </ul>
            </QuietSection>
          ))
        )}
      </div>

      <FileStoryPanel
        open={storyFile !== null}
        fileName={
          storyFile
            ? storyFile.relative_path.split(/[\\/]/).pop() ||
              storyFile.relative_path
            : ""
        }
        directPlay={storyFile?.direct_play ?? []}
        log={fileLog.data}
        loading={fileLog.isPending}
        error={fileLog.isError ? fileLog.error.message : null}
        onClose={closeStory}
      />
    </div>
  );
}
