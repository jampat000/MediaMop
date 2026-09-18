import { useEffect, useState, type CSSProperties, type ReactNode } from "react";

import { ChooseTracksPanel } from "../../components/processing/choose-tracks-panel";
import { DirectPlayLine } from "../../components/processing/direct-play-line";
import { PageLoading } from "../../components/shared/page-loading";
import { useMeQuery } from "../../lib/auth/queries";
import {
  PROCESSING_FILE_STATUS_LABELS,
  processingFileLogDownloadPath,
  type ProcessingFile,
  type ProcessingFileLog,
  type ProcessingFileStatus,
  type ProcessingFileTracks,
  type ProcessingManualPlanChoice,
} from "../../lib/processing/files-api";
import {
  useForgetProcessingFile,
  useMoveProcessingFileToTop,
  useProcessProcessingFileNow,
  useProcessingCheckLibraryAgain,
  useProcessingFileLog,
  useProcessingFileTracks,
  useProcessingWhyHeld,
  useRequeueProcessingFile,
  useRequeueProcessingFiles,
  useProcessingFilesQuery,
  useSubmitProcessingManualPlan,
} from "../../lib/processing/files-queries";
import { useProcessingLibrariesQuery } from "../../lib/processing/libraries-queries";
import {
  mmActionButtonClass,
  mmEditableTextFieldClass,
  mmSelectFieldClass,
} from "../../lib/ui/mm-control-roles";
import { mmStatusPillClass } from "../../lib/ui/mm-status-tone";
import { parseAppDate, useAppDateFormatter } from "../../lib/ui/mm-format-date";
import { usePauseQuery } from "../../lib/pause/pause-queries";
import { plural } from "../../lib/ui/mm-plural";

function canEdit(role: string | undefined): boolean {
  return role === "operator" || role === "admin";
}

/** The nine states the band draws and the list can filter to. `passed_through` and
 *  `rejected` are real statuses but not filters, so they are counted in the caption
 *  instead — see `elsewhere` below. */
type BucketStatus =
  | "processing"
  | "unprocessed"
  | "on_hold"
  | "out_of_schedule"
  | "blocked_upstream"
  | "skipped"
  | "disabled"
  | "processed"
  | "processing_failed";

/** Buckets in the order an operator reads them: working, waiting, withheld, finished. */
const BUCKETS: BucketStatus[] = [
  "processing",
  "unprocessed",
  "on_hold",
  "out_of_schedule",
  "blocked_upstream",
  "skipped",
  "disabled",
  "processed",
  "processing_failed",
];

const ACTIONABLE_STATUSES = new Set<ProcessingFileStatus>([
  "unprocessed",
  "processing_failed",
  "on_hold",
  "out_of_schedule",
  "blocked_upstream",
]);

/** One line each, saying what the state means. Shown under the count in the lead band. */
const BUCKET_HINTS: Record<BucketStatus, string> = {
  processing: "Being rewritten now",
  unprocessed: "Ready for the next slot",
  on_hold: "Held until it can run",
  out_of_schedule: "Outside its schedule window",
  blocked_upstream: "Waiting on a media manager",
  skipped: "Nothing to change",
  disabled: "Its library is switched off",
  processed: "Handed back clean",
  processing_failed: "Waiting for review",
};

/**
 * How each state's pill reads. Three states (`skipped`, `passed_through`, `rejected`)
 * used to have no rule at all and fell through to a bare outlined pill, visibly unlike
 * their eight siblings. This map is exhaustive over `ProcessingFileStatus`, so the
 * compiler makes the next state a decision rather than another accidental gap.
 */
type ProcessingStatusTone = "healthy" | "info" | "warning" | "neutral";

const PROCESSING_STATUS_TONES: Record<
  ProcessingFileStatus,
  ProcessingStatusTone
> = {
  unprocessed: "healthy",
  processed: "healthy",
  // A validated, unchanged hand-back is a finished good outcome, the same as `processed`.
  passed_through: "healthy",
  processing: "info",
  // Everything an operator may need to act on shares one tone. `rejected` (dropped in
  // favour of a replacement) belongs here rather than reading as benign, and no state is
  // painted louder than a real failure.
  processing_failed: "warning",
  on_hold: "warning",
  out_of_schedule: "warning",
  blocked_upstream: "warning",
  rejected: "warning",
  // Deliberately colourless: "Weir looked and there was nothing to do" is not an outcome
  // worth a colour, and neither is a library the operator switched off themselves.
  skipped: "neutral",
  disabled: "neutral",
};

function statusPillClass(status: ProcessingFileStatus): string {
  return mmStatusPillClass(PROCESSING_STATUS_TONES[status]);
}

function fileStatusFromUrl(): ProcessingFileStatus | undefined {
  if (typeof window === "undefined") return undefined;
  const value = new URLSearchParams(window.location.search).get("status");
  return BUCKETS.includes(value as BucketStatus)
    ? (value as ProcessingFileStatus)
    : undefined;
}

function pathFromUrl(): string {
  if (typeof window === "undefined") return "";
  return new URLSearchParams(window.location.search).get("path") ?? "";
}

function replaceFileFilterInUrl(
  status: ProcessingFileStatus | undefined,
): void {
  if (typeof window === "undefined") return;
  const params = new URLSearchParams(window.location.search);
  if (status) params.set("status", status);
  else params.delete("status");
  const suffix = params.toString();
  window.history.replaceState(
    window.history.state,
    "",
    `${window.location.pathname}${suffix ? `?${suffix}` : ""}${window.location.hash}`,
  );
}

function fileHasPausedReason(file: ProcessingFile): boolean {
  return (
    file.status === "out_of_schedule" &&
    file.status_reason.toLowerCase().includes("processing is paused")
  );
}

function displayStatusForFile(
  file: ProcessingFile,
  processingPaused: boolean,
): string {
  if (!fileHasPausedReason(file))
    return PROCESSING_FILE_STATUS_LABELS[file.status];
  return processingPaused ? "Paused" : "Needs re-check";
}

function displayReasonForFile(
  file: ProcessingFile,
  processingPaused: boolean,
): string {
  if (fileHasPausedReason(file) && !processingPaused) {
    return "This file was last checked while processing was paused. The pause has ended, so its saved status needs refreshing.";
  }
  return file.status_reason;
}

function guidanceForFile(
  file: ProcessingFile,
  processingPaused: boolean,
): { title: string; next: string } {
  if (fileHasPausedReason(file)) {
    if (!processingPaused) {
      return {
        title: "Refresh this file's status.",
        next: "Use Check again. Weir will apply the current schedule, readiness, size, and path rules without deleting the original file.",
      };
    }
    return {
      title: "Processing is paused.",
      next: "Use Resume at the top of the page when you want queued work to continue. Check again is only needed after changing this file or its library.",
    };
  }
  switch (file.status) {
    case "unprocessed":
      return {
        title: "Ready to process.",
        next: "Start it now or move it to the front of the queue.",
      };
    case "processing_failed":
      return {
        title: "This attempt failed.",
        next: "Fix the reason and use Try again, or use Pass through unchanged when this is an intentional edge case you want delivered without your rules.",
      };
    case "skipped":
      return {
        title: "This file does not match the library rules.",
        next: "Change the named library rule and use Check again, or pass this one file through unchanged when it is a legitimate exception.",
      };
    case "on_hold":
      return {
        title: "Waiting for the file to settle.",
        next: "Finish the copy or import, then use Check again. Weir will not touch a changing file.",
      };
    case "blocked_upstream":
      return {
        title: "The media manager still owns this file.",
        next: "Use Why is this held? for the live manager answer, or Check again after the import finishes.",
      };
    case "out_of_schedule":
      return {
        title: "This library is outside its schedule.",
        next: "It will be picked up when the window opens; use Check again if you changed the schedule.",
      };
    case "disabled":
      return {
        title: "This library is switched off.",
        next: "Turn the library on in Processing → Libraries before processing its files.",
      };
    case "processed":
      return {
        title: "The last pass finished.",
        next: "Open Processing record for the exact plan and outcome.",
      };
    case "processing":
      return {
        title: "Weir is working on this file.",
        next: "No action is needed. Open Processing record after it finishes.",
      };
  }
  return {
    title: "This file needs a review.",
    next: "Open its processing record and choose the action that matches the reason.",
  };
}

function holdReleaseLabel(
  holdUntil: string,
  formatDate: (iso: string) => string,
): string {
  const at = parseAppDate(holdUntil);
  if (Number.isNaN(at.getTime())) return "";
  const seconds = Math.round((at.getTime() - Date.now()) / 1000);
  if (seconds <= 0) return "Due to be re-checked on the next scan.";
  if (seconds < 90)
    return `Ready in about ${seconds}s (${formatDate(holdUntil)}).`;
  const minutes = Math.round(seconds / 60);
  return `Ready in about ${minutes} min (${formatDate(holdUntil)}).`;
}

function humanSize(bytes: number): string {
  if (!bytes) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value >= 10 || unit === 0 ? Math.round(value) : value.toFixed(1)} ${units[unit]}`;
}

type ProcessingFact = { label: string; value: string };

const PROCESSING_FACT_LABELS: Record<string, string> = {
  user_message: "What happened",
  result: "Result",
  outcome: "Outcome",
  reason: "Reason",
  source_path: "Source file",
  source_file: "Source file",
  output_path: "Output file",
  output_file: "Output file",
  source_size_bytes: "Source size",
  output_size_bytes: "Output size",
  bytes_saved: "Space saved",
  net_bytes_saved: "Net space saved",
  cleanup_result: "Source cleanup",
  cleanup_reason: "Cleanup detail",
  output_validation: "Output validation",
  validation_result: "Validation",
  plan_summary: "Processing plan",
  duration_seconds: "Processing time",
  changed: "Media changed",
};

const TECHNICAL_FACT_KEYS = new Set([
  "job_id",
  "library_id",
  "file_id",
  "schema_version",
  "dedupe_key",
  "fingerprint",
  "source_fingerprint",
  "payload_json",
  "ffmpeg_argv",
]);

function humanFactLabel(key: string): string {
  return (
    PROCESSING_FACT_LABELS[key] ??
    key.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase())
  );
}

function humanFactValue(key: string, value: unknown): string | null {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") {
    if (key.endsWith("_bytes")) return humanSize(value);
    if (key.endsWith("_seconds")) {
      return value >= 60
        ? `${Math.round(value / 60)} min (${Math.round(value)} sec)`
        : `${Math.round(value)} sec`;
    }
    return String(value);
  }
  if (typeof value === "string") return value;
  if (Array.isArray(value) && value.every((item) => typeof item !== "object")) {
    return value.map(String).join(", ");
  }
  return null;
}

function processingFacts(detail: Record<string, unknown>): ProcessingFact[] {
  const facts: Array<ProcessingFact & { rank: number }> = [];
  const visit = (value: Record<string, unknown>, depth: number) => {
    for (const [key, item] of Object.entries(value)) {
      if (TECHNICAL_FACT_KEYS.has(key) || key.endsWith("_json")) continue;
      const shown = humanFactValue(key, item);
      if (shown !== null) {
        facts.push({
          label: humanFactLabel(key),
          value: shown,
          rank: PROCESSING_FACT_LABELS[key] ? 0 : 1,
        });
      } else if (
        depth < 1 &&
        item &&
        typeof item === "object" &&
        !Array.isArray(item)
      ) {
        visit(item as Record<string, unknown>, depth + 1);
      }
    }
  };
  visit(detail, 0);
  return facts
    .sort((left, right) => left.rank - right.rank)
    .slice(0, 16)
    .map(({ label, value }) => ({ label, value }));
}

function timestampLabel(
  value: string | null,
  formatDate: (iso: string) => string,
): string {
  if (!value) return "Not recorded";
  const at = parseAppDate(value);
  if (Number.isNaN(at.getTime())) return "Not recorded";
  const elapsedSeconds = Math.max(
    0,
    Math.round((Date.now() - at.getTime()) / 1000),
  );
  let relative: string;
  if (elapsedSeconds < 60) relative = "just now";
  else if (elapsedSeconds < 3600)
    relative = `${Math.floor(elapsedSeconds / 60)} min ago`;
  else if (elapsedSeconds < 86_400)
    relative = `${Math.floor(elapsedSeconds / 3600)} hr ago`;
  else
    relative = `${plural(Math.floor(elapsedSeconds / 86_400), "day", "days")} ago`;
  return `${formatDate(value)} · ${relative}`;
}

function QuietSection({
  headingId,
  heading,
  aside,
  children,
  "data-testid": dataTestId,
}: {
  headingId: string;
  heading: string;
  aside?: ReactNode;
  children: ReactNode;
  "data-testid"?: string;
}) {
  return (
    <section
      className="mm-quiet-section"
      aria-labelledby={headingId}
      data-testid={dataTestId}
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

/**
 * The lead: every state Weir files work into, each one a filter into the list below. In a
 * row each segment is as wide as the number of files in it; where nine of them cannot fit
 * one line the primitive restacks them into a labelled list by itself, and this page sets
 * nothing but `--mm-flow-share` to get that.
 *
 * The counts come from `status_counts`, which the server computes with
 * `SELECT status, COUNT(*) FROM files [WHERE library_id = ?] GROUP BY status` — so it
 * ignores the status, path and limit filters entirely and only narrows to a chosen
 * library. That is what makes a band honest here: paginating with "Show at most" cannot
 * move these numbers. The one thing it does not know about is the path filter, and the
 * caption says so rather than letting the band quietly disagree with the list.
 *
 * Nine segments is the full filter set, so turning the old pill row into the band lost no
 * filter. The band wraps to a second line on a narrow panel, by itself.
 */
function FileFlowBand({
  counts,
  active,
  outOfScheduleLabel,
  onSelect,
}: {
  counts: Record<string, number>;
  active: ProcessingFileStatus | undefined;
  outOfScheduleLabel: string;
  onSelect: (status: ProcessingFileStatus | undefined) => void;
}) {
  const stages = BUCKETS.map((status) => ({
    status,
    label:
      status === "out_of_schedule"
        ? outOfScheduleLabel
        : PROCESSING_FILE_STATUS_LABELS[status],
    count: counts[status] ?? 0,
  }));
  const total = stages.reduce((sum, stage) => sum + stage.count, 0);
  return (
    <div className="mm-lead-band" data-testid="processing-files-buckets">
      {stages.map((stage) => {
        const live = stage.status === "processing" && stage.count > 0;
        const modifier =
          stage.count === 0
            ? " mm-lead-band__segment--empty"
            : live
              ? " mm-lead-band__segment--live"
              : "";
        // The same weighting Overview uses: the raw count, floored at 6% of the total so
        // an empty state still reads as a state.
        const share = total === 0 ? 1 : Math.max(stage.count, total * 0.06);
        const selected = active === stage.status;
        return (
          <button
            key={stage.status}
            type="button"
            className={`mm-lead-band__segment${modifier}`}
            style={{ "--mm-flow-share": share } as CSSProperties}
            aria-pressed={selected}
            onClick={() => onSelect(selected ? undefined : stage.status)}
            data-testid={`processing-files-bucket-${stage.status}`}
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
            <span className="mm-lead-band__hint">
              {BUCKET_HINTS[stage.status]}
            </span>
            <span className="mm-lead-band__go" aria-hidden="true">
              {selected ? "Clear →" : "Filter →"}
            </span>
          </button>
        );
      })}
    </div>
  );
}

/**
 * The Processing Files screen.
 *
 * This is the screen that answers "why isn't this file processing?". Processing used to
 * decide and move on — the reason existed only inside the scan — so a file that was
 * held, out of schedule, or waiting on an import simply never appeared anywhere (#334).
 *
 * Laid out in the Weir content language (docs/design/content-language.md): the state band
 * leads, then the worklist, quietly. There is no figure row — a worklist has no single
 * number that carries it, and an invented hero is worse than no hero.
 */
export function ProcessingFilesSection() {
  const formatDate = useAppDateFormatter();
  const me = useMeQuery();
  const libraries = useProcessingLibrariesQuery();
  const [libraryId, setLibraryId] = useState<number | undefined>(undefined);
  const [fileStatus, setFileStatus] = useState<
    ProcessingFileStatus | undefined
  >(fileStatusFromUrl);
  const [pathContains, setPathContains] = useState(pathFromUrl);
  const [limit, setLimit] = useState(200);
  const [notice, setNotice] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(() => new Set());
  const [bulkWorking, setBulkWorking] = useState(false);

  const files = useProcessingFilesQuery({
    library_id: libraryId,
    file_status: fileStatus,
    path_contains: pathContains.trim() || undefined,
    limit,
  });
  const pause = usePauseQuery();
  const forget = useForgetProcessingFile();
  const moveToTopMutation = useMoveProcessingFileToTop();
  const requeueOne = useRequeueProcessingFile();
  const requeueMany = useRequeueProcessingFiles();
  const whyHeld = useProcessingWhyHeld();
  const fileLog = useProcessingFileLog();
  const processNow = useProcessProcessingFileNow();
  const checkAgain = useProcessingCheckLibraryAgain();
  const [openLog, setOpenLog] = useState<ProcessingFileLog | null>(null);
  const fileTracks = useProcessingFileTracks();
  const submitManualPlan = useSubmitProcessingManualPlan();
  const [tracksFile, setTracksFile] = useState<ProcessingFile | null>(null);
  const [tracksData, setTracksData] = useState<ProcessingFileTracks | null>(
    null,
  );
  const [tracksError, setTracksError] = useState<string | null>(null);
  const [manualPlanError, setManualPlanError] = useState<string | null>(null);
  const editable = canEdit(me.data?.role);

  useEffect(() => {
    const visibleIds = new Set(
      (files.data?.files ?? []).map((file) => file.id),
    );
    setSelectedIds((previous) => {
      const next = new Set([...previous].filter((id) => visibleIds.has(id)));
      return next.size === previous.size ? previous : next;
    });
  }, [files.data?.files]);

  if (files.isLoading) return <PageLoading label="Loading files" />;

  const page = files.data;
  const counts = page?.status_counts ?? {};
  const rows = page?.files ?? [];
  const processingPaused = pause.data?.paused === true;
  const stalePausedRows = processingPaused
    ? 0
    : rows.filter(fileHasPausedReason).length;
  const outOfScheduleLabel = processingPaused
    ? "Paused"
    : stalePausedRows > 0 && stalePausedRows === (counts.out_of_schedule ?? 0)
      ? "Needs re-check"
      : stalePausedRows > 0
        ? "Schedule / re-check"
        : PROCESSING_FILE_STATUS_LABELS.out_of_schedule;
  const selectedRows = rows.filter((file) => selectedIds.has(file.id));
  const selectedActionableRows = selectedRows.filter((file) =>
    ACTIONABLE_STATUSES.has(file.status),
  );

  // Every file Weir holds, and the part of it the band draws. `status_counts` covers all
  // eleven statuses; BUCKETS draws nine, so `passed_through` and `rejected` are counted
  // and said out loud in the caption rather than quietly dropped.
  const censusTotal = Object.values(counts).reduce((sum, n) => sum + n, 0);
  const shownInBand = BUCKETS.reduce(
    (sum, status) => sum + (counts[status] ?? 0),
    0,
  );
  const elsewhere = censusTotal - shownInBand;
  // The same arithmetic the old "Needs action" tile did. It moves into the band's caption
  // rather than being a fourth number in a box above the band.
  const needsAction =
    (counts.processing_failed ?? 0) +
    (counts.on_hold ?? 0) +
    (counts.blocked_upstream ?? 0) +
    stalePausedRows;

  const selectFileStatus = (next: ProcessingFileStatus | undefined) => {
    setFileStatus(next);
    replaceFileFilterInUrl(next);
  };

  const toggleSelected = (id: number) => {
    setSelectedIds((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAllVisible = () => {
    setSelectedIds((previous) => {
      const next = new Set(previous);
      const allSelected =
        rows.length > 0 && rows.every((file) => next.has(file.id));
      if (allSelected) rows.forEach((file) => next.delete(file.id));
      else rows.forEach((file) => next.add(file.id));
      return next;
    });
  };

  const requeue = async (file: ProcessingFile) => {
    setNotice(null);
    try {
      const result = await requeueOne.mutateAsync(file.id);
      setNotice(result.detail);
    } catch {
      setNotice("That file could not be queued again.");
    }
  };

  const requeueFiltered = async () => {
    setNotice(null);
    try {
      // The same filter the list is showing, so what gets queued is what is on screen.
      const result = await requeueMany.mutateAsync({
        library_id: libraryId,
        file_status: fileStatus,
        path_contains: pathContains || undefined,
        limit,
      });
      setNotice(result.detail);
    } catch {
      setNotice("Those files could not be queued again.");
    }
  };

  const askWhyHeld = async (file: ProcessingFile) => {
    setNotice(null);
    try {
      const answer = await whyHeld.mutateAsync(file.id);
      // The evaluator's reasons are already written for operators, so they are shown
      // unchanged rather than re-worded here.
      setNotice(
        answer.reasons.length
          ? answer.reasons.join(" ")
          : "The media managers had nothing to say about this file.",
      );
    } catch {
      setNotice("Weir could not ask why that file is held.");
    }
  };

  const processFileNow = async (file: ProcessingFile) => {
    setNotice(null);
    const library = libraries.data?.find((l) => l.id === file.library_id);
    try {
      await processNow.mutateAsync({
        relative_media_path: file.relative_path,
        media_scope: library?.media_type === "tv" ? "tv" : "movie",
        library_id: file.library_id,
      });
      setNotice(
        "Queued this file for processing. It starts as soon as there is capacity.",
      );
    } catch {
      setNotice("That file could not be queued for processing.");
    }
  };

  const passThroughFile = async (file: ProcessingFile) => {
    const confirmed = window.confirm(
      "Pass this file through unchanged?\n\nWeir will bypass audio, subtitle, and metadata rules, copy and validate the original in this library's output folder, then remove the watched source using the normal successful-cleanup rules. Readiness checks still apply, so an active download will remain untouched.",
    );
    if (!confirmed) return;

    setNotice(null);
    const library = libraries.data?.find((item) => item.id === file.library_id);
    try {
      await processNow.mutateAsync({
        relative_media_path: file.relative_path,
        media_scope: library?.media_type === "tv" ? "tv" : "movie",
        library_id: file.library_id,
        pass_through_unchanged: true,
      });
      setNotice(
        "Queued to pass through unchanged. Weir will validate the output before removing the watched source.",
      );
    } catch {
      setNotice(
        "That file could not be queued for pass-through. Refresh the row and review its library paths.",
      );
    }
  };

  const checkFileAgain = async (file: ProcessingFile) => {
    setNotice(null);
    const library = libraries.data?.find((item) => item.id === file.library_id);
    try {
      await checkAgain.mutateAsync({
        media_scope: library?.media_type === "tv" ? "tv" : "movie",
        library_id: file.library_id,
      });
      setNotice(
        `Queued a fresh check for ${file.relative_path}. Weir will re-evaluate the file and queue it when it is ready.`,
      );
    } catch {
      setNotice(
        "That library could not be checked again. Review its saved watched folder and try again.",
      );
    }
  };

  const runSelectedActions = async () => {
    if (selectedActionableRows.length === 0) {
      setNotice("Select a waiting, failed, or held file to give it an action.");
      return;
    }
    setBulkWorking(true);
    setNotice(null);
    let started = 0;
    let checked = 0;
    try {
      const checkedLibraries = new Set<number>();
      for (const file of selectedActionableRows) {
        if (file.status === "processing_failed") {
          await requeueOne.mutateAsync(file.id);
          started += 1;
        } else if (file.status === "unprocessed") {
          const library = libraries.data?.find(
            (item) => item.id === file.library_id,
          );
          await processNow.mutateAsync({
            relative_media_path: file.relative_path,
            media_scope: library?.media_type === "tv" ? "tv" : "movie",
            library_id: file.library_id,
          });
          started += 1;
        } else if (!checkedLibraries.has(file.library_id)) {
          const library = libraries.data?.find(
            (item) => item.id === file.library_id,
          );
          await checkAgain.mutateAsync({
            media_scope: library?.media_type === "tv" ? "tv" : "movie",
            library_id: file.library_id,
          });
          checkedLibraries.add(file.library_id);
          checked += 1;
        }
      }
      setSelectedIds(new Set());
      const parts: string[] = [];
      if (started) parts.push(`${plural(started, "file", "files")} queued`);
      if (checked)
        parts.push(`${plural(checked, "library", "libraries")} rechecked`);
      setNotice(
        `${parts.join("; ")}. Weir will update the file state as work moves.`,
      );
    } catch {
      setNotice(
        "Some selected actions could not be completed. Refresh the list and review the remaining rows.",
      );
    } finally {
      setBulkWorking(false);
    }
  };

  const showLog = async (file: ProcessingFile) => {
    setNotice(null);
    try {
      const log = await fileLog.mutateAsync(file.id);
      if (log.entries.length === 0) {
        setNotice(
          "Weir has not processed this file yet, so there is no record to show.",
        );
        return;
      }
      setOpenLog(log);
    } catch {
      setNotice("Weir could not read that file's processing record.");
    }
  };

  const openChooseTracks = async (file: ProcessingFile) => {
    setNotice(null);
    setTracksFile(file);
    setTracksData(null);
    setTracksError(null);
    setManualPlanError(null);
    try {
      const tracks = await fileTracks.mutateAsync(file.id);
      setTracksData(tracks);
    } catch {
      setTracksError(
        "Weir could not read this file's tracks. Refresh and try again.",
      );
    }
  };

  const closeChooseTracks = () => {
    setTracksFile(null);
    setTracksData(null);
    setTracksError(null);
    setManualPlanError(null);
  };

  const submitChooseTracks = async (choice: ProcessingManualPlanChoice) => {
    if (!tracksFile) return;
    setManualPlanError(null);
    try {
      await submitManualPlan.mutateAsync({ id: tracksFile.id, choice });
      setNotice(
        `Queued your track choice for ${tracksFile.relative_path}. Weir will check the file again before running the pass.`,
      );
      closeChooseTracks();
    } catch {
      setManualPlanError(
        "That track choice could not be queued. Fix the reported problem, or refresh the tracks and try again.",
      );
    }
  };

  const moveToTop = async (file: ProcessingFile) => {
    setNotice(null);
    try {
      // The server decides whether the move was possible and says so in words the
      // screen shows unchanged — it knows whether the work had already started.
      const result = await moveToTopMutation.mutateAsync(file.id);
      setNotice(result.detail);
    } catch {
      setNotice("That file could not be moved to the front of the queue.");
    }
  };

  const removeFile = async (file: ProcessingFile) => {
    setNotice(null);
    try {
      await forget.mutateAsync(file.id);
    } catch {
      setNotice("That file could not be removed from the list.");
    }
  };

  return (
    <div
      className="mm-processing-files mm-quiet-stack"
      data-testid="processing-files-section"
    >
      <div className="mm-lead">
        {censusTotal === 0 ? (
          <p
            className="mm-quiet-note"
            data-testid="processing-files-flow-empty"
          >
            No files match. Weir records a file the first time a scan looks at
            it.
          </p>
        ) : (
          <FileFlowBand
            counts={counts}
            active={fileStatus}
            outOfScheduleLabel={outOfScheduleLabel}
            onSelect={selectFileStatus}
          />
        )}

        {/* The caption explains the band. With no band drawn there is nothing for it to
            explain, and the empty sentence above has already said the whole story. */}
        {censusTotal === 0 ? null : (
          <p
            className="mm-lead-caption"
            data-testid="processing-files-flow-caption"
          >
            <span>
              Click a state to filter the list, or click it again to clear.
              {libraryId === undefined
                ? ""
                : " These counts are for the selected library."}
              {pathContains.trim()
                ? " The path filter narrows the list below, not these counts."
                : ""}
            </span>
            <span>
              {needsAction > 0
                ? `${needsAction.toLocaleString()} ${needsAction === 1 ? "file needs" : "files need"} action.`
                : "Nothing needs action."}
              {elsewhere > 0
                ? ` ${elsewhere.toLocaleString()} more in states this band does not show.`
                : ""}
            </span>
          </p>
        )}
      </div>

      <QuietSection
        headingId="processing-files-worklist-heading"
        heading="Give every file a useful next step."
        aside={
          fileStatus ? (
            <button
              type="button"
              className="mm-quiet-link"
              onClick={() => selectFileStatus(undefined)}
            >
              Show all {censusTotal.toLocaleString()} files →
            </button>
          ) : (
            <span className="text-xs text-[var(--mm-text3)]">
              {censusTotal.toLocaleString()} files
            </span>
          )
        }
      >
        <p className="mm-quiet-note">
          Every file Weir has seen. Select rows to start, retry, or re-check
          them together. Pass through unchanged is the explicit exception: it
          validates an unchanged output first, then performs the library&apos;s
          normal successful source cleanup.
        </p>

        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          <label className="block text-sm">
            <span className="text-[var(--mm-text2)]">Library</span>
            <select
              className={mmSelectFieldClass}
              value={libraryId ?? ""}
              onChange={(e) =>
                setLibraryId(
                  e.target.value ? Number(e.target.value) : undefined,
                )
              }
            >
              <option value="">All libraries</option>
              {(libraries.data ?? []).map((library) => (
                <option key={library.id} value={library.id}>
                  {library.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            <span className="text-[var(--mm-text2)]">Path contains</span>
            <input
              className={mmEditableTextFieldClass}
              value={pathContains}
              placeholder="part of a file or folder name"
              onChange={(e) => setPathContains(e.target.value)}
            />
          </label>
          <label className="block text-sm">
            <span className="text-[var(--mm-text2)]">Show at most</span>
            <select
              className={mmSelectFieldClass}
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
            >
              {[50, 200, 500, 1000].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        </div>

        {editable && rows.length > 0 ? (
          <div
            className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-[var(--mm-border)] pb-4"
            data-testid="processing-files-selection-bar"
          >
            <label className="inline-flex items-center gap-2 text-sm text-[var(--mm-text2)]">
              <input
                type="checkbox"
                className="[accent-color:var(--mm-accent)]"
                checked={
                  rows.length > 0 &&
                  rows.every((file) => selectedIds.has(file.id))
                }
                onChange={selectAllVisible}
                data-testid="processing-files-select-all"
              />
              Select all visible
            </label>
            <span className="text-xs text-[var(--mm-text3)]">
              {selectedIds.size} selected · choose rows to run the right action
              for each state.
            </span>
            <button
              type="button"
              className={mmActionButtonClass({
                variant: "secondary",
                disabled: bulkWorking || selectedActionableRows.length === 0,
              })}
              onClick={() => void runSelectedActions()}
              disabled={bulkWorking || selectedActionableRows.length === 0}
              data-testid="processing-files-run-selected"
            >
              {bulkWorking ? "Working…" : "Run selected actions"}
            </button>
            {selectedRows.some(
              (file) => !ACTIONABLE_STATUSES.has(file.status),
            ) ? (
              <span className="text-xs text-[var(--mm-text3)]">
                Done, skipped, processing, and library-off rows are
                informational only.
              </span>
            ) : null}
          </div>
        ) : null}

        {/* Bulk requeue acts on the filter currently on screen, so what gets queued is
            what is being looked at. Only offered when the filter is narrow enough to mean
            something — "requeue everything" is not a button anyone should have. */}
        {editable && fileStatus === "processing_failed" ? (
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <button
              type="button"
              className={mmActionButtonClass({ variant: "secondary" })}
              onClick={() => void requeueFiltered()}
              data-testid="processing-files-requeue-filtered"
              disabled={requeueMany.isPending || rows.length === 0}
            >
              {requeueMany.isPending
                ? "Queueing…"
                : `Try all ${rows.length} again`}
            </button>
            <span className="text-xs text-[var(--mm-text3)]">
              Queues everything matching the filters above, up to {limit} files.
            </span>
          </div>
        ) : null}

        {notice ? (
          <p
            className="mt-4 text-sm font-medium text-[var(--mm-text1)]"
            role="status"
            data-testid="processing-files-notice"
          >
            {notice}
          </p>
        ) : null}

        {openLog ? (
          <div className="mt-5" data-testid="processing-file-log-panel">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate font-medium text-[var(--mm-text1)]">
                  {openLog.relative_path}
                </p>
                <p className="text-xs text-[var(--mm-text3)]">
                  {plural(openLog.entries.length, "record", "records")} ·{" "}
                  {openLog.retention_days === 0
                    ? "kept forever"
                    : `kept for ${openLog.retention_days} days`}
                </p>
              </div>
              <div className="flex gap-2">
                {/* A real link, not a scripted save: the browser handles the download and
                  the filename comes from the server. */}
                <a
                  className={mmActionButtonClass({ variant: "tertiary" })}
                  href={processingFileLogDownloadPath(openLog.file_id)}
                  data-testid="processing-file-log-download"
                >
                  Download
                </a>
                <button
                  type="button"
                  className={mmActionButtonClass({ variant: "tertiary" })}
                  onClick={() => setOpenLog(null)}
                  data-testid="processing-file-log-close"
                >
                  Close
                </button>
              </div>
            </div>
            <ul className="mt-3">
              {openLog.entries.map((entry) => {
                const facts = processingFacts(entry.detail);
                return (
                  <li
                    key={entry.id}
                    className="border-b border-[var(--mm-border)] py-4 last:border-b-0"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <p className="text-sm font-medium text-[var(--mm-text1)]">
                          {entry.title || "Processing record"}
                        </p>
                        <p className="mt-0.5 text-xs text-[var(--mm-text3)]">
                          {formatDate(entry.recorded_at)}
                        </p>
                      </div>
                      {/* The outcome word itself says what happened; the chip is a shape,
                        not a verdict, so it stays tone-neutral rather than painting every
                        record — including a failed one — healthy green as it used to. */}
                      <span className={mmStatusPillClass("neutral")}>
                        {(entry.outcome || "recorded").replaceAll("_", " ")}
                      </span>
                    </div>
                    {facts.length > 0 ? (
                      <dl className="mt-3 grid gap-x-6 gap-y-3 sm:grid-cols-2">
                        {facts.map((fact, index) => (
                          <div key={`${fact.label}-${index}`}>
                            <dt className="text-[0.68rem] font-semibold uppercase tracking-[0.12em] text-[var(--mm-text3)]">
                              {fact.label}
                            </dt>
                            <dd className="mt-1 break-words text-sm text-[var(--mm-text2)] [overflow-wrap:anywhere]">
                              {fact.value}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    ) : (
                      <p className="mt-3 text-sm text-[var(--mm-text2)]">
                        No additional human-readable detail was recorded for
                        this pass.
                      </p>
                    )}
                    <details className="mt-3">
                      <summary className="cursor-pointer text-xs font-medium text-[var(--mm-text3)]">
                        Technical record
                      </summary>
                      <pre className="mt-2 max-h-64 overflow-auto rounded border border-[var(--mm-border)] p-2 text-xs text-[var(--mm-text3)]">
                        {JSON.stringify(entry.detail, null, 2)}
                      </pre>
                    </details>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : null}

        {rows.length === 0 ? (
          // When Weir holds nothing at all the lead already said so, and the strongest
          // empty wins outright rather than saying it twice. This line is for the other
          // empty: files exist, but the filters on this screen hide all of them.
          censusTotal === 0 ? null : (
            <p className="mt-5 text-sm text-[var(--mm-text3)]">
              No files match. Weir records a file the first time a scan looks at
              it.
            </p>
          )
        ) : (
          <ul className="mt-2">
            {rows.map((file) => {
              const guidance = guidanceForFile(file, processingPaused);
              return (
                // The box goes, but a hairline stays: this is the densest row anywhere in
                // Processing — seven facts and up to seven buttons — and without a
                // separator one file's actions run straight into the next file's path.
                // The intrinsic size is re-stated here because the shared rule in
                // weir-shell.css is sized against the old bordered card.
                <li
                  key={file.id}
                  className="border-b border-[var(--mm-border)] py-4 last:border-b-0 [contain-intrinsic-size:auto_15rem]"
                  data-testid={`processing-file-${file.id}`}
                >
                  <div className="mm-processing-file-card">
                    {editable ? (
                      <label
                        className="mm-processing-file-select"
                        title="Select this file for a bulk action"
                      >
                        <input
                          type="checkbox"
                          className="[accent-color:var(--mm-accent)]"
                          checked={selectedIds.has(file.id)}
                          onChange={() => toggleSelected(file.id)}
                          aria-label={`Select ${file.relative_path}`}
                          data-testid={`processing-file-select-${file.id}`}
                        />
                      </label>
                    ) : null}
                    <div className="mm-processing-file-content min-w-0 flex-1">
                      <div className="mm-processing-file-main min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="break-words font-medium text-[var(--mm-text1)] [overflow-wrap:anywhere]">
                            {file.relative_path}
                          </p>
                          <span className={statusPillClass(file.status)}>
                            {displayStatusForFile(file, processingPaused)}
                          </span>
                        </div>
                        <p className="mt-1 text-xs text-[var(--mm-text3)]">
                          {file.library_name} · {humanSize(file.size_bytes)} ·{" "}
                          {file.failure_attempts} failure
                          {file.failure_attempts === 1 ? "" : "s"}
                        </p>
                        {/* Three labelled facts, not a table and no longer three little
                          boxes: whitespace and the eyebrow type carry them. */}
                        <dl
                          className="mt-3 grid gap-x-6 gap-y-2 sm:grid-cols-3"
                          data-testid={`processing-file-timestamps-${file.id}`}
                        >
                          {[
                            {
                              label: "First seen",
                              value: timestampLabel(
                                file.created_at,
                                formatDate,
                              ),
                            },
                            {
                              label: "Last checked",
                              value: timestampLabel(
                                file.last_seen_at,
                                formatDate,
                              ),
                            },
                            {
                              label: "Last processing attempt",
                              value: timestampLabel(
                                file.last_attempt_at,
                                formatDate,
                              ),
                            },
                          ].map((fact) => (
                            <div key={fact.label} className="min-w-0">
                              <dt className="text-[0.62rem] font-bold uppercase tracking-[0.08em] text-[var(--mm-text3)]">
                                {fact.label}
                              </dt>
                              <dd className="mt-0.5 text-[0.73rem] leading-[1.4] text-[var(--mm-text2)] tabular-nums">
                                {fact.value}
                              </dd>
                            </div>
                          ))}
                        </dl>
                        {/* The reason is the whole point of this screen, so it is not hidden
                      behind a detail view. */}
                        <p className="mt-1 text-sm text-[var(--mm-text2)]">
                          {displayReasonForFile(file, processingPaused)}
                        </p>
                        {/* A hold with no release time reads as held forever. When Weir
                      knows when the wait ends, it says so; when the wait is on a writer
                      rather than the clock, hold_until is null and nothing is invented. */}
                        {file.status === "on_hold" && file.hold_until ? (
                          <p
                            className="mt-1 text-xs text-[var(--mm-text3)]"
                            data-testid={`processing-file-hold-until-${file.id}`}
                          >
                            {holdReleaseLabel(file.hold_until, formatDate)}
                          </p>
                        ) : null}
                        <DirectPlayLine
                          directPlay={file.direct_play}
                          testId={`processing-file-direct-play-${file.id}`}
                        />
                        {/* The guidance keeps its accent eyebrow but loses its tinted well:
                          below the lead, hierarchy is type and whitespace. */}
                        <div className="mt-3">
                          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--mm-accent-bright)]">
                            Next step
                          </p>
                          <p className="mt-1 text-sm font-medium text-[var(--mm-text1)]">
                            {guidance.title}
                          </p>
                          <p className="mt-1 text-xs leading-5 text-[var(--mm-text2)]">
                            {guidance.next}
                          </p>
                        </div>
                      </div>
                      {editable ? (
                        <div className="mm-processing-file-actions flex flex-wrap gap-2">
                          {/* Only offered where it can do something: a file that is running
                      cannot be started earlier, and a button that looked like it worked
                      would be worse than no button. */}
                          {file.status === "unprocessed" ? (
                            <button
                              type="button"
                              className={mmActionButtonClass({
                                variant: "tertiary",
                              })}
                              onClick={() => void moveToTop(file)}
                              data-testid={`processing-file-move-to-top-${file.id}`}
                              title="Puts this file's queued work ahead of everything else waiting."
                            >
                              Move to top
                            </button>
                          ) : null}
                          {file.status === "processing_failed" ? (
                            <button
                              type="button"
                              className={mmActionButtonClass({
                                variant: "secondary",
                              })}
                              onClick={() => void requeue(file)}
                              data-testid={`processing-file-requeue-${file.id}`}
                              title="Tries this file again now, ignoring the automatic backoff and attempt limit."
                            >
                              Try again
                            </button>
                          ) : null}
                          {file.status === "blocked_upstream" ||
                          file.status === "on_hold" ? (
                            <button
                              type="button"
                              className={mmActionButtonClass({
                                variant: "tertiary",
                              })}
                              onClick={() => void askWhyHeld(file)}
                              data-testid={`processing-file-why-held-${file.id}`}
                              title="Asks every media manager covering this library what it is doing with this file, right now."
                            >
                              Why is this held?
                            </button>
                          ) : null}
                          {file.status === "on_hold" ? (
                            <button
                              type="button"
                              className={mmActionButtonClass({
                                variant: "secondary",
                              })}
                              onClick={() => void openChooseTracks(file)}
                              data-testid={`processing-file-choose-tracks-${file.id}`}
                              title="Re-reads this file's tracks and lets you pick which ones to keep by hand, instead of the saved rules."
                            >
                              Choose tracks
                            </button>
                          ) : null}
                          {file.status === "on_hold" ||
                          file.status === "blocked_upstream" ||
                          file.status === "skipped" ||
                          file.status === "out_of_schedule" ? (
                            <button
                              type="button"
                              className={mmActionButtonClass({
                                variant: "secondary",
                              })}
                              onClick={() => void checkFileAgain(file)}
                              data-testid={`processing-file-check-again-${file.id}`}
                              title="Re-checks this library now and queues files that are ready."
                            >
                              Check again
                            </button>
                          ) : null}
                          {file.status === "unprocessed" ? (
                            <button
                              type="button"
                              className={mmActionButtonClass({
                                variant: "tertiary",
                              })}
                              onClick={() => void processFileNow(file)}
                              data-testid={`processing-file-process-now-${file.id}`}
                              title="Queues a remux pass for this file straight away."
                            >
                              Process now
                            </button>
                          ) : null}
                          {file.status !== "processing" &&
                          file.status !== "processed" &&
                          file.status !== "disabled" ? (
                            <button
                              type="button"
                              className={mmActionButtonClass({
                                variant: "secondary",
                              })}
                              onClick={() => void passThroughFile(file)}
                              data-testid={`processing-file-pass-through-${file.id}`}
                              title="Skips your track and metadata rules, safely places an unchanged validated copy in the output folder, then performs normal successful source cleanup."
                            >
                              Pass through unchanged
                            </button>
                          ) : null}
                          <button
                            type="button"
                            className={mmActionButtonClass({
                              variant: "tertiary",
                            })}
                            onClick={() => void showLog(file)}
                            data-testid={`processing-file-log-${file.id}`}
                            title="What Weir did to this file, and why. Kept beyond the activity feed."
                          >
                            Processing record
                          </button>
                          <button
                            type="button"
                            className={mmActionButtonClass({
                              variant: "tertiary",
                            })}
                            onClick={() => void removeFile(file)}
                            data-testid={`processing-file-forget-${file.id}`}
                            title="Removes Weir's record of this file. The file on disk is untouched."
                          >
                            Remove from list
                          </button>
                        </div>
                      ) : null}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </QuietSection>

      <ChooseTracksPanel
        open={tracksFile !== null}
        fileName={tracksFile?.relative_path ?? ""}
        tracks={tracksData ?? undefined}
        loading={fileTracks.isPending}
        loadError={tracksError}
        submitting={submitManualPlan.isPending}
        submitError={manualPlanError}
        onClose={closeChooseTracks}
        onSubmit={(choice) => void submitChooseTracks(choice)}
      />
    </div>
  );
}
