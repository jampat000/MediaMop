import { useEffect, useState } from "react";

import { PageLoading } from "../../components/shared/page-loading";
import { useMeQuery } from "../../lib/auth/queries";
import {
  REFINER_FILE_STATUS_LABELS,
  refinerFileLogDownloadPath,
  type RefinerFile,
  type RefinerFileLog,
  type RefinerFileStatus,
} from "../../lib/refiner/files-api";
import {
  useForgetRefinerFile,
  useMoveRefinerFileToTop,
  useProcessRefinerFileNow,
  useRefinerCheckLibraryAgain,
  useRefinerFileLog,
  useRefinerWhyHeld,
  useRequeueRefinerFile,
  useRequeueRefinerFiles,
  useRefinerFilesQuery,
} from "../../lib/refiner/files-queries";
import { useRefinerLibrariesQuery } from "../../lib/refiner/libraries-queries";
import {
  mmActionButtonClass,
  mmEditableTextFieldClass,
  mmSelectFieldClass,
} from "../../lib/ui/mm-control-roles";
import { parseAppDate, useAppDateFormatter } from "../../lib/ui/mm-format-date";
import { useSuitePauseQuery } from "../../lib/suite/pause-queries";

function canEdit(role: string | undefined): boolean {
  return role === "operator" || role === "admin";
}

/** Buckets in the order an operator reads them: working, waiting, withheld, finished. */
const BUCKETS: RefinerFileStatus[] = [
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

const ACTIONABLE_STATUSES = new Set<RefinerFileStatus>([
  "unprocessed",
  "processing_failed",
  "on_hold",
  "out_of_schedule",
  "blocked_upstream",
]);

function fileStatusFromUrl(): RefinerFileStatus | undefined {
  if (typeof window === "undefined") return undefined;
  const value = new URLSearchParams(window.location.search).get("status");
  return BUCKETS.includes(value as RefinerFileStatus)
    ? (value as RefinerFileStatus)
    : undefined;
}

function pathFromUrl(): string {
  if (typeof window === "undefined") return "";
  return new URLSearchParams(window.location.search).get("path") ?? "";
}

function replaceFileFilterInUrl(status: RefinerFileStatus | undefined): void {
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

function fileHasPausedReason(file: RefinerFile): boolean {
  return (
    file.status === "out_of_schedule" &&
    file.status_reason.toLowerCase().includes("processing is paused")
  );
}

function displayStatusForFile(
  file: RefinerFile,
  processingPaused: boolean,
): string {
  if (!fileHasPausedReason(file))
    return REFINER_FILE_STATUS_LABELS[file.status];
  return processingPaused ? "Paused" : "Needs re-check";
}

function displayReasonForFile(
  file: RefinerFile,
  processingPaused: boolean,
): string {
  if (fileHasPausedReason(file) && !processingPaused) {
    return "This file was last checked while processing was paused. The pause has ended, so its saved status needs refreshing.";
  }
  return file.status_reason;
}

function guidanceForFile(
  file: RefinerFile,
  processingPaused: boolean,
): { title: string; next: string } {
  if (fileHasPausedReason(file)) {
    if (!processingPaused) {
      return {
        title: "Refresh this file's status.",
        next: "Use Check again. MediaMop will apply the current schedule, readiness, size, and path rules without deleting the original file.",
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
        next: "Fix the reason above, then use Try again. Automatic retry status is shown here.",
      };
    case "skipped":
      return {
        title: "This file does not match the library rules.",
        next: "The reason above names the rule. Change that library rule and use Check again if you want MediaMop to reconsider it.",
      };
    case "on_hold":
      return {
        title: "Waiting for the file to settle.",
        next: "Finish the copy or import, then use Check again. MediaMop will not touch a changing file.",
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
        next: "Enable the library in Refiner → Libraries before processing its files.",
      };
    case "processed":
      return {
        title: "The last pass finished.",
        next: "Open Processing record for the exact plan and outcome.",
      };
    case "processing":
      return {
        title: "Refiner is working on this file.",
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
  else relative = `${Math.floor(elapsedSeconds / 86_400)} day(s) ago`;
  return `${formatDate(value)} · ${relative}`;
}

/**
 * The Refiner Files screen.
 *
 * This is the screen that answers "why isn't this file processing?". Refiner used to
 * decide and move on — the reason existed only inside the scan — so a file that was
 * held, out of schedule, or waiting on an import simply never appeared anywhere (#334).
 */
export function RefinerFilesSection() {
  const formatDate = useAppDateFormatter();
  const me = useMeQuery();
  const libraries = useRefinerLibrariesQuery();
  const [libraryId, setLibraryId] = useState<number | undefined>(undefined);
  const [fileStatus, setFileStatus] = useState<RefinerFileStatus | undefined>(
    fileStatusFromUrl,
  );
  const [pathContains, setPathContains] = useState(pathFromUrl);
  const [limit, setLimit] = useState(200);
  const [notice, setNotice] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(() => new Set());
  const [bulkWorking, setBulkWorking] = useState(false);

  const files = useRefinerFilesQuery({
    library_id: libraryId,
    file_status: fileStatus,
    path_contains: pathContains.trim() || undefined,
    limit,
  });
  const suitePause = useSuitePauseQuery();
  const forget = useForgetRefinerFile();
  const moveToTopMutation = useMoveRefinerFileToTop();
  const requeueOne = useRequeueRefinerFile();
  const requeueMany = useRequeueRefinerFiles();
  const whyHeld = useRefinerWhyHeld();
  const fileLog = useRefinerFileLog();
  const processNow = useProcessRefinerFileNow();
  const checkAgain = useRefinerCheckLibraryAgain();
  const [openLog, setOpenLog] = useState<RefinerFileLog | null>(null);
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
  const processingPaused = suitePause.data?.paused === true;
  const stalePausedRows = processingPaused
    ? 0
    : rows.filter(fileHasPausedReason).length;
  const outOfScheduleLabel = processingPaused
    ? "Paused"
    : stalePausedRows > 0 && stalePausedRows === (counts.out_of_schedule ?? 0)
      ? "Needs re-check"
      : stalePausedRows > 0
        ? "Schedule / re-check"
        : REFINER_FILE_STATUS_LABELS.out_of_schedule;
  const selectedRows = rows.filter((file) => selectedIds.has(file.id));
  const selectedActionableRows = selectedRows.filter((file) =>
    ACTIONABLE_STATUSES.has(file.status),
  );

  const selectFileStatus = (next: RefinerFileStatus | undefined) => {
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

  const requeue = async (file: RefinerFile) => {
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

  const askWhyHeld = async (file: RefinerFile) => {
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
      setNotice("MediaMop could not ask why that file is held.");
    }
  };

  const processFileNow = async (file: RefinerFile) => {
    setNotice(null);
    const library = libraries.data?.find((l) => l.id === file.library_id);
    try {
      await processNow.mutateAsync({
        relative_media_path: file.relative_path,
        media_scope: library?.media_scope === "tv" ? "tv" : "movie",
        library_id: file.library_id,
      });
      setNotice(
        "Queued this file for processing. It starts as soon as there is capacity.",
      );
    } catch {
      setNotice("That file could not be queued for processing.");
    }
  };

  const checkFileAgain = async (file: RefinerFile) => {
    setNotice(null);
    const library = libraries.data?.find((item) => item.id === file.library_id);
    try {
      await checkAgain.mutateAsync({
        media_scope: library?.media_scope === "tv" ? "tv" : "movie",
        library_id: file.library_id,
      });
      setNotice(
        `Queued a fresh check for ${file.relative_path}. MediaMop will re-evaluate the file and queue it when it is ready.`,
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
            media_scope: library?.media_scope === "tv" ? "tv" : "movie",
            library_id: file.library_id,
          });
          started += 1;
        } else if (!checkedLibraries.has(file.library_id)) {
          const library = libraries.data?.find(
            (item) => item.id === file.library_id,
          );
          await checkAgain.mutateAsync({
            media_scope: library?.media_scope === "tv" ? "tv" : "movie",
            library_id: file.library_id,
          });
          checkedLibraries.add(file.library_id);
          checked += 1;
        }
      }
      setSelectedIds(new Set());
      const parts: string[] = [];
      if (started) parts.push(`${started} file(s) queued`);
      if (checked) parts.push(`${checked} library/libraries rechecked`);
      setNotice(
        `${parts.join("; ")}. MediaMop will update the file state as work moves.`,
      );
    } catch {
      setNotice(
        "Some selected actions could not be completed. Refresh the list and review the remaining rows.",
      );
    } finally {
      setBulkWorking(false);
    }
  };

  const showLog = async (file: RefinerFile) => {
    setNotice(null);
    try {
      const log = await fileLog.mutateAsync(file.id);
      if (log.entries.length === 0) {
        setNotice(
          "MediaMop has not processed this file yet, so there is no record to show.",
        );
        return;
      }
      setOpenLog(log);
    } catch {
      setNotice("MediaMop could not read that file's processing record.");
    }
  };

  const moveToTop = async (file: RefinerFile) => {
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

  const removeFile = async (file: RefinerFile) => {
    setNotice(null);
    try {
      await forget.mutateAsync(file.id);
    } catch {
      setNotice("That file could not be removed from the list.");
    }
  };

  return (
    <div
      className="mm-refiner-files space-y-5"
      data-testid="refiner-files-section"
    >
      <div className="mm-refiner-workbench-intro">
        <div>
          <p className="mm-page__eyebrow">Refiner workbench</p>
          <h2 className="text-xl font-semibold tracking-tight text-[var(--mm-text1)]">
            Give every file a useful next step.
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-[var(--mm-text2)]">
            This is the control room for files Refiner has seen. Select rows to
            start, retry, or re-check them together; the original media file is
            never removed by these actions.
          </p>
        </div>
        <div
          className="mm-refiner-workbench-stats"
          aria-label="File work summary"
        >
          <div>
            <span>Needs action</span>
            <strong>
              {(counts.processing_failed ?? 0) +
                (counts.on_hold ?? 0) +
                (counts.blocked_upstream ?? 0) +
                stalePausedRows}
            </strong>
          </div>
          <div>
            <span>Ready</span>
            <strong>{counts.unprocessed ?? 0}</strong>
          </div>
          <div>
            <span>In progress</span>
            <strong>{counts.processing ?? 0}</strong>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2" data-testid="refiner-files-buckets">
        <button
          type="button"
          className={mmActionButtonClass({
            variant: fileStatus === undefined ? "primary" : "tertiary",
          })}
          onClick={() => selectFileStatus(undefined)}
        >
          All (
          {rows.length === 0 && !page
            ? 0
            : Object.values(counts).reduce((a, b) => a + b, 0)}
          )
        </button>
        {BUCKETS.map((status) => (
          <button
            key={status}
            type="button"
            className={mmActionButtonClass({
              variant: fileStatus === status ? "primary" : "tertiary",
            })}
            onClick={() => selectFileStatus(status)}
            data-testid={`refiner-files-bucket-${status}`}
          >
            {status === "out_of_schedule"
              ? outOfScheduleLabel
              : REFINER_FILE_STATUS_LABELS[status]}{" "}
            ({counts[status] ?? 0})
          </button>
        ))}
      </div>

      {editable && rows.length > 0 ? (
        <div
          className="mm-refiner-selection-bar"
          data-testid="refiner-files-selection-bar"
        >
          <label className="inline-flex items-center gap-2 text-sm text-[var(--mm-text2)]">
            <input
              type="checkbox"
              checked={
                rows.length > 0 &&
                rows.every((file) => selectedIds.has(file.id))
              }
              onChange={selectAllVisible}
              data-testid="refiner-files-select-all"
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
            data-testid="refiner-files-run-selected"
          >
            {bulkWorking ? "Working…" : "Run selected actions"}
          </button>
          {selectedRows.some(
            (file) => !ACTIONABLE_STATUSES.has(file.status),
          ) ? (
            <span className="text-xs text-[var(--mm-text3)]">
              Done, skipped, processing, and library-off rows are informational
              only.
            </span>
          ) : null}
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-3">
        <label className="block text-sm">
          <span className="text-[var(--mm-text2)]">Library</span>
          <select
            className={mmSelectFieldClass}
            value={libraryId ?? ""}
            onChange={(e) =>
              setLibraryId(e.target.value ? Number(e.target.value) : undefined)
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

      {/* Bulk requeue acts on the filter currently on screen, so what gets queued is
          what is being looked at. Only offered when the filter is narrow enough to mean
          something — "requeue everything" is not a button anyone should have. */}
      {editable && fileStatus === "processing_failed" ? (
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className={mmActionButtonClass({ variant: "secondary" })}
            onClick={() => void requeueFiltered()}
            data-testid="refiner-files-requeue-filtered"
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

      {openLog ? (
        <div
          className="rounded border border-[var(--mm-border)] p-3"
          data-testid="refiner-file-log-panel"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate font-medium text-[var(--mm-text1)]">
                {openLog.relative_path}
              </p>
              <p className="text-xs text-[var(--mm-text3)]">
                {openLog.entries.length} record(s) ·{" "}
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
                href={refinerFileLogDownloadPath(openLog.file_id)}
                data-testid="refiner-file-log-download"
              >
                Download
              </a>
              <button
                type="button"
                className={mmActionButtonClass({ variant: "tertiary" })}
                onClick={() => setOpenLog(null)}
                data-testid="refiner-file-log-close"
              >
                Close
              </button>
            </div>
          </div>
          <ul className="mt-3 space-y-3">
            {openLog.entries.map((entry) => {
              const facts = processingFacts(entry.detail);
              return (
                <li
                  key={entry.id}
                  className="rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-3"
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
                    <span className="mm-refiner-status mm-refiner-status--processed">
                      {(entry.outcome || "recorded").replaceAll("_", " ")}
                    </span>
                  </div>
                  {facts.length > 0 ? (
                    <dl className="mt-3 grid gap-2 sm:grid-cols-2">
                      {facts.map((fact, index) => (
                        <div
                          key={`${fact.label}-${index}`}
                          className="rounded border border-[var(--mm-border)] px-3 py-2"
                        >
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
                      No additional human-readable detail was recorded for this
                      pass.
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

      {notice ? (
        <p
          className="rounded border border-[var(--mm-border)] px-3 py-2 text-sm"
          role="status"
          data-testid="refiner-files-notice"
        >
          {notice}
        </p>
      ) : null}

      {rows.length === 0 ? (
        <p className="text-sm text-[var(--mm-text3)]">
          No files match. Refiner records a file the first time a scan looks at
          it.
        </p>
      ) : (
        <ul className="space-y-2">
          {rows.map((file) => {
            const guidance = guidanceForFile(file, processingPaused);
            return (
              <li
                key={file.id}
                className="rounded border border-[var(--mm-border)] p-3"
                data-testid={`refiner-file-${file.id}`}
              >
                <div className="mm-refiner-file-card">
                  {editable ? (
                    <label
                      className="mm-refiner-file-select"
                      title="Select this file for a bulk action"
                    >
                      <input
                        type="checkbox"
                        checked={selectedIds.has(file.id)}
                        onChange={() => toggleSelected(file.id)}
                        aria-label={`Select ${file.relative_path}`}
                        data-testid={`refiner-file-select-${file.id}`}
                      />
                    </label>
                  ) : null}
                  <div className="mm-refiner-file-content min-w-0 flex-1">
                    <div className="mm-refiner-file-main min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="break-words font-medium text-[var(--mm-text1)] [overflow-wrap:anywhere]">
                          {file.relative_path}
                        </p>
                        <span
                          className={`mm-refiner-status mm-refiner-status--${file.status}`}
                        >
                          {displayStatusForFile(file, processingPaused)}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-[var(--mm-text3)]">
                        {file.library_name} · {humanSize(file.size_bytes)} ·{" "}
                        {file.failure_attempts} failure
                        {file.failure_attempts === 1 ? "" : "s"}
                      </p>
                      <dl
                        className="mm-refiner-file-timeline"
                        data-testid={`refiner-file-timestamps-${file.id}`}
                      >
                        <div>
                          <dt>First seen</dt>
                          <dd>{timestampLabel(file.created_at, formatDate)}</dd>
                        </div>
                        <div>
                          <dt>Last checked</dt>
                          <dd>
                            {timestampLabel(file.last_seen_at, formatDate)}
                          </dd>
                        </div>
                        <div>
                          <dt>Last processing attempt</dt>
                          <dd>
                            {timestampLabel(file.last_attempt_at, formatDate)}
                          </dd>
                        </div>
                      </dl>
                      {/* The reason is the whole point of this screen, so it is not hidden
                      behind a detail view. */}
                      <p className="mt-1 text-sm text-[var(--mm-text2)]">
                        {displayReasonForFile(file, processingPaused)}
                      </p>
                      {/* A hold with no release time reads as held forever. When MediaMop
                      knows when the wait ends, it says so; when the wait is on a writer
                      rather than the clock, hold_until is null and nothing is invented. */}
                      {file.status === "on_hold" && file.hold_until ? (
                        <p
                          className="mt-1 text-xs text-[var(--mm-text3)]"
                          data-testid={`refiner-file-hold-until-${file.id}`}
                        >
                          {holdReleaseLabel(file.hold_until, formatDate)}
                        </p>
                      ) : null}
                      <div className="mm-refiner-next-step mt-3">
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
                      <div className="mm-refiner-file-actions flex flex-wrap gap-2">
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
                            data-testid={`refiner-file-move-to-top-${file.id}`}
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
                            data-testid={`refiner-file-requeue-${file.id}`}
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
                            data-testid={`refiner-file-why-held-${file.id}`}
                            title="Asks every media manager covering this library what it is doing with this file, right now."
                          >
                            Why is this held?
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
                            data-testid={`refiner-file-check-again-${file.id}`}
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
                            data-testid={`refiner-file-process-now-${file.id}`}
                            title="Queues a remux pass for this file straight away."
                          >
                            Process now
                          </button>
                        ) : null}
                        <button
                          type="button"
                          className={mmActionButtonClass({
                            variant: "tertiary",
                          })}
                          onClick={() => void showLog(file)}
                          data-testid={`refiner-file-log-${file.id}`}
                          title="What MediaMop did to this file, and why. Kept beyond the activity feed."
                        >
                          Processing record
                        </button>
                        <button
                          type="button"
                          className={mmActionButtonClass({
                            variant: "tertiary",
                          })}
                          onClick={() => void removeFile(file)}
                          data-testid={`refiner-file-forget-${file.id}`}
                          title="Removes MediaMop's record of this file. The file on disk is untouched."
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
    </div>
  );
}
