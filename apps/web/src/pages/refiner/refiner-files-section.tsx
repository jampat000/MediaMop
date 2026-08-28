import { useState } from "react";

import { PageLoading } from "../../components/shared/page-loading";
import { useMeQuery } from "../../lib/auth/queries";
import {
  REFINER_FILE_STATUS_LABELS,
  type RefinerFile,
  type RefinerFileStatus,
} from "../../lib/refiner/files-api";
import {
  useForgetRefinerFile,
  useRefinerFilesQuery,
} from "../../lib/refiner/files-queries";
import { useRefinerLibrariesQuery } from "../../lib/refiner/libraries-queries";
import {
  mmActionButtonClass,
  mmEditableTextFieldClass,
  mmSelectFieldClass,
} from "../../lib/ui/mm-control-roles";

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
  "disabled",
  "processed",
  "processing_failed",
];

function holdReleaseLabel(holdUntil: string): string {
  const at = new Date(holdUntil);
  if (Number.isNaN(at.getTime())) return "";
  const seconds = Math.round((at.getTime() - Date.now()) / 1000);
  if (seconds <= 0) return "Due to be re-checked on the next scan.";
  if (seconds < 90)
    return `Ready in about ${seconds}s (${at.toLocaleTimeString()}).`;
  const minutes = Math.round(seconds / 60);
  return `Ready in about ${minutes} min (${at.toLocaleTimeString()}).`;
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

/**
 * The Refiner Files screen.
 *
 * This is the screen that answers "why isn't this file processing?". Refiner used to
 * decide and move on — the reason existed only inside the scan — so a file that was
 * held, out of schedule, or waiting on an import simply never appeared anywhere (#334).
 */
export function RefinerFilesSection() {
  const me = useMeQuery();
  const libraries = useRefinerLibrariesQuery();
  const [libraryId, setLibraryId] = useState<number | undefined>(undefined);
  const [fileStatus, setFileStatus] = useState<RefinerFileStatus | undefined>(
    undefined,
  );
  const [pathContains, setPathContains] = useState("");
  const [limit, setLimit] = useState(200);
  const [notice, setNotice] = useState<string | null>(null);

  const files = useRefinerFilesQuery({
    library_id: libraryId,
    file_status: fileStatus,
    path_contains: pathContains.trim() || undefined,
    limit,
  });
  const forget = useForgetRefinerFile();
  const editable = canEdit(me.data?.role);

  if (files.isLoading) return <PageLoading label="Loading files" />;

  const page = files.data;
  const counts = page?.status_counts ?? {};
  const rows = page?.files ?? [];

  const removeFile = async (file: RefinerFile) => {
    setNotice(null);
    try {
      await forget.mutateAsync(file.id);
    } catch {
      setNotice("That file could not be removed from the list.");
    }
  };

  return (
    <div className="space-y-4" data-testid="refiner-files-section">
      <p className="text-sm text-[var(--mm-text2)]">
        Every file Refiner has looked at, and what it decided. A file that is
        not being processed says why.
      </p>

      <div className="flex flex-wrap gap-2" data-testid="refiner-files-buckets">
        <button
          type="button"
          className={mmActionButtonClass({
            variant: fileStatus === undefined ? "primary" : "tertiary",
          })}
          onClick={() => setFileStatus(undefined)}
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
            onClick={() => setFileStatus(status)}
            data-testid={`refiner-files-bucket-${status}`}
          >
            {REFINER_FILE_STATUS_LABELS[status]} ({counts[status] ?? 0})
          </button>
        ))}
      </div>

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
          {rows.map((file) => (
            <li
              key={file.id}
              className="rounded border border-[var(--mm-border)] p-3"
              data-testid={`refiner-file-${file.id}`}
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-medium text-[var(--mm-text1)]">
                    {file.relative_path}
                  </p>
                  <p className="text-xs text-[var(--mm-text3)]">
                    {file.library_name} ·{" "}
                    {REFINER_FILE_STATUS_LABELS[file.status]} ·{" "}
                    {humanSize(file.size_bytes)}
                  </p>
                  {/* The reason is the whole point of this screen, so it is not hidden
                      behind a detail view. */}
                  <p className="mt-1 text-sm text-[var(--mm-text2)]">
                    {file.status_reason}
                  </p>
                  {/* A hold with no release time reads as held forever. When MediaMop
                      knows when the wait ends, it says so; when the wait is on a writer
                      rather than the clock, hold_until is null and nothing is invented. */}
                  {file.status === "on_hold" && file.hold_until ? (
                    <p
                      className="mt-1 text-xs text-[var(--mm-text3)]"
                      data-testid={`refiner-file-hold-until-${file.id}`}
                    >
                      {holdReleaseLabel(file.hold_until)}
                    </p>
                  ) : null}
                </div>
                {editable ? (
                  <button
                    type="button"
                    className={mmActionButtonClass({ variant: "tertiary" })}
                    onClick={() => void removeFile(file)}
                    data-testid={`refiner-file-forget-${file.id}`}
                    title="Removes MediaMop's record of this file. The file on disk is untouched."
                  >
                    Remove from list
                  </button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
