/**
 * "In hand" — what MediaMop is currently responsible for (#463).
 *
 * MediaMop is a stage in the middle of a pipeline. A media manager downloads a release into a
 * completed folder, MediaMop takes it, works on it, and writes it to an output folder the
 * manager then imports. It never sees the library on your storage, so this screen deliberately
 * never claims to: the subject is **custody**, not a library.
 *
 * It answers four questions, in this order:
 *   1. what arrived and is waiting
 *   2. what is in hand right now, and what is happening to each file
 *   3. what is stuck — and therefore missing from the manager
 *   4. what was handed back
 */

import { useCallback, useMemo, useState } from "react";
import { DirectPlayLine } from "../../components/refiner/direct-play-line";
import { FileStoryPanel } from "../../components/refiner/file-story-panel";
import { Link } from "react-router-dom";
import { PageLoading } from "../../components/shared/page-loading";
import { ApiEntryError } from "../../components/shared/api-entry-error";
import {
  REFINER_FILE_STATUS_LABELS,
  type RefinerFile,
} from "../../lib/refiner/files-api";
import {
  useRefinerFileLog,
  useRefinerFilesQuery,
} from "../../lib/refiner/files-queries";
import { useRefinerLibrariesQuery } from "../../lib/refiner/libraries-queries";
import { useRefinerOverviewStatsQuery } from "../../lib/refiner/queries";

/** Statuses that mean the file is MediaMop's responsibility right now. */
const IN_HAND: ReadonlySet<string> = new Set([
  "unprocessed",
  "processing",
  "on_hold",
  "out_of_schedule",
  "blocked_upstream",
]);

/** Statuses that mean the manager will not see this file until somebody acts. */
const STUCK: ReadonlySet<string> = new Set(["processing_failed"]);

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
function mediaFacts(file: RefinerFile): string {
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
  if (status === "blocked_upstream") return "mm-inhand-row__state--held";
  return "";
}

function FileRow({
  file,
  onOpen,
}: {
  file: RefinerFile;
  onOpen: (file: RefinerFile) => void;
}): React.ReactElement {
  const name = file.relative_path.split(/[\\/]/).pop() || file.relative_path;
  const facts = mediaFacts(file);
  const eta = formatEta(file.progress_eta_seconds);
  const percent = file.progress_percent;

  return (
    <li className="mm-inhand-row" data-testid="in-hand-row">
      <div className="mm-inhand-row__main">
        <button
          type="button"
          className="mm-inhand-row__name"
          title={`What happened to ${file.relative_path}`}
          onClick={() => onOpen(file)}
        >
          {name}
        </button>
        <span className="mm-inhand-row__facts">
          {[formatBytes(file.size_bytes), facts].filter(Boolean).join(" · ")}
        </span>
        <DirectPlayLine
          directPlay={file.direct_play}
          testId={`in-hand-direct-play-${file.id}`}
        />
      </div>

      <div className="mm-inhand-row__state">
        <span className={statusToneClass(file.status)}>
          {REFINER_FILE_STATUS_LABELS[file.status] ?? file.status}
          {file.blocked_by_connection
            ? ` — ${file.blocked_by_connection} is importing it`
            : ""}
        </span>
        {/* The reason sentence is written for the operator by the pass itself. */}
        {file.status_reason ? (
          <span className="mm-inhand-row__reason">{file.status_reason}</span>
        ) : null}
        {percent !== null ? (
          <span className="mm-inhand-row__progress">
            <span
              className="mm-inhand-row__progress-track"
              role="progressbar"
              aria-valuenow={Math.round(percent)}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={`Processing ${name}`}
            >
              <span
                className="mm-inhand-row__progress-fill"
                style={{ width: `${Math.max(2, Math.round(percent))}%` }}
              />
            </span>
            <span className="mm-inhand-row__progress-text">
              {Math.round(percent)}%{eta ? ` · ${eta}` : ""}
            </span>
          </span>
        ) : null}
      </div>
    </li>
  );
}

export function InHandPage(): React.ReactElement {
  const files = useRefinerFilesQuery({ limit: 200 });
  const today = useRefinerOverviewStatsQuery(1);
  const libraries = useRefinerLibrariesQuery();
  const fileLog = useRefinerFileLog();
  const [storyFile, setStoryFile] = useState<RefinerFile | null>(null);

  const openStory = useCallback(
    (file: RefinerFile) => {
      setStoryFile(file);
      fileLog.mutate(file.id);
    },
    [fileLog],
  );
  const closeStory = useCallback(() => setStoryFile(null), []);

  const grouped = useMemo(() => {
    const rows = (files.data?.files ?? []).filter((f) => IN_HAND.has(f.status));
    const byLibrary = new Map<string, RefinerFile[]>();
    for (const row of rows) {
      const key = row.library_name || "Unknown library";
      const list = byLibrary.get(key);
      if (list) list.push(row);
      else byLibrary.set(key, [row]);
    }
    // Working files first inside each library — they are what an operator looks for.
    for (const list of byLibrary.values()) {
      list.sort((a, b) => {
        const rank = (f: RefinerFile) => (f.status === "processing" ? 0 : 1);
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
  const waiting = counts.unprocessed ?? 0;
  const working = counts.processing ?? 0;
  const inHandTotal = [...IN_HAND].reduce((n, s) => n + (counts[s] ?? 0), 0);
  const watchedFolder = libraries.data?.[0]?.watched_folder ?? "";
  const outputFolder = libraries.data?.[0]?.output_folder ?? "";

  return (
    <div className="mm-page">
      <header className="mm-page__intro">
        <p className="mm-page__eyebrow">
          Between your manager and your storage
        </p>
        <h1 className="mm-page__title">In hand</h1>
        <p className="mm-page__lead">
          Files MediaMop is responsible for right now, between your media
          manager handing them over and getting them back.
        </p>
      </header>

      {/* Where MediaMop sits, made literal. Nobody should have to guess. */}
      <section className="mm-inhand-flow" aria-label="Where these files are">
        <div className="mm-inhand-flow__stage">
          <p className="mm-inhand-flow__label">Arriving</p>
          <p className="mm-inhand-flow__figure">{waiting}</p>
          <p className="mm-inhand-flow__detail">
            waiting{watchedFolder ? ` in ${watchedFolder}` : ""}
          </p>
        </div>
        <div className="mm-inhand-flow__arrow" aria-hidden="true">
          →
        </div>
        <div className="mm-inhand-flow__stage mm-inhand-flow__stage--active">
          <p className="mm-inhand-flow__label">In MediaMop&rsquo;s hands</p>
          <p className="mm-inhand-flow__figure">{inHandTotal}</p>
          <p className="mm-inhand-flow__detail">
            {working} being worked on right now
          </p>
        </div>
        <div className="mm-inhand-flow__arrow" aria-hidden="true">
          →
        </div>
        <div className="mm-inhand-flow__stage">
          <p className="mm-inhand-flow__label">Handed back today</p>
          <p className="mm-inhand-flow__figure mm-status-text--healthy">
            {today.data?.files_processed ?? 0}
          </p>
          <p className="mm-inhand-flow__detail">
            {today.data
              ? `${formatBytes(today.data.net_space_saved_bytes)} saved${
                  outputFolder ? ` · ${outputFolder}` : ""
                }`
              : "—"}
          </p>
        </div>
      </section>

      {stuck.length > 0 ? (
        <section className="mm-inhand-stuck" aria-labelledby="in-hand-stuck">
          <h2 id="in-hand-stuck" className="mm-inhand-stuck__title">
            {stuck.length === 1
              ? "1 file is stuck in MediaMop's hands"
              : `${stuck.length} files are stuck in MediaMop's hands`}
          </h2>
          <p className="mm-inhand-stuck__body">
            Your media manager will not see these until they are dealt with. The
            originals are untouched in the watched folder.
          </p>
          <ul className="mm-inhand-list">
            {stuck.map((file) => (
              <FileRow key={file.id} file={file} onOpen={openStory} />
            ))}
          </ul>
          <Link className="mm-inhand-stuck__link" to="/refiner">
            Open Refiner to deal with them
          </Link>
        </section>
      ) : null}

      {grouped.length === 0 ? (
        <section className="mm-inhand-empty">
          <h2 className="mm-inhand-empty__title">Nothing in hand</h2>
          <p className="mm-inhand-empty__body">
            Every file your manager handed over has been dealt with and passed
            back. New arrivals in a watched folder will show up here.
          </p>
        </section>
      ) : (
        grouped.map(([libraryName, rows]) => (
          <section
            key={libraryName}
            className="mm-inhand-group"
            aria-label={libraryName}
          >
            <h2 className="mm-inhand-group__title">
              {libraryName}
              <span className="mm-inhand-group__count">
                {rows.length === 1 ? "1 file" : `${rows.length} files`}
              </span>
            </h2>
            <ul className="mm-inhand-list">
              {rows.map((file) => (
                <FileRow key={file.id} file={file} onOpen={openStory} />
              ))}
            </ul>
          </section>
        ))
      )}

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
