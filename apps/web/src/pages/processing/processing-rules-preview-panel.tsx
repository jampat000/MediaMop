import { useEffect, useId, useRef, useState } from "react";

import { ServerFolderPickerButton } from "../../components/ui/server-folder-picker-button";
import type { ProcessingRuleSetWrite } from "../../lib/processing/libraries-api";
import {
  useProcessingLibrariesQuery,
  useProcessingRulesPreview,
} from "../../lib/processing/libraries-queries";
import type {
  ProcessingRulesPreviewResult,
  ProcessingRulesPreviewTrack,
} from "../../lib/processing/rules-preview-api";
import {
  mmActionButtonClass,
  mmEditableTextFieldClass,
  mmSelectFieldClass,
} from "../../lib/ui/mm-control-roles";

/** Rules edits change so often (every keystroke, debounced) that re-running on every one of them
 * would spam the single-preview-at-a-time server gate; this is long enough to wait for a pause in
 * typing without feeling sluggish. */
const RERUN_DEBOUNCE_MS = 700;

function errorText(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function formatBytes(value: number | null | undefined): string | null {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    return null;
  }
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

function joinPath(folder: string, fileName: string): string {
  const trimmedFolder = folder.trim().replace(/[/\\]+$/, "");
  const trimmedFile = fileName.trim().replace(/^[/\\]+/, "");
  if (!trimmedFolder) return trimmedFile;
  if (!trimmedFile) return trimmedFolder;
  const separator = trimmedFolder.includes("\\") ? "\\" : "/";
  return `${trimmedFolder}${separator}${trimmedFile}`;
}

const TRACK_TYPE_LABELS: Record<ProcessingRulesPreviewTrack["type"], string> = {
  video: "Video",
  audio: "Audio",
  subtitle: "Subtitle",
};

function TrackRow({ track }: { track: ProcessingRulesPreviewTrack }) {
  const kept = track.action === "keep";
  return (
    <tr className="border-t border-[var(--mm-border)] align-top">
      <td className="px-3 py-2 text-[var(--mm-text3)]">{track.index}</td>
      <td className="px-3 py-2">{TRACK_TYPE_LABELS[track.type]}</td>
      <td className="px-3 py-2">{track.codec || "—"}</td>
      <td className="px-3 py-2">
        {track.language ? track.language.toUpperCase() : "—"}
      </td>
      <td className="max-w-[12rem] truncate px-3 py-2" title={track.title}>
        {track.title || "—"}
      </td>
      <td className="px-3 py-2">
        {track.type === "audio" && track.channels > 0 ? track.channels : "—"}
      </td>
      <td className="px-3 py-2">
        <span
          className={
            kept
              ? "rounded-full border border-emerald-400/40 bg-emerald-400/10 px-2 py-0.5 text-xs font-semibold text-emerald-300"
              : "rounded-full border border-red-400/40 bg-red-400/10 px-2 py-0.5 text-xs font-semibold text-red-300"
          }
        >
          {kept ? "Keep" : "Drop"}
        </span>
      </td>
      <td className="px-3 py-2 text-xs text-[var(--mm-text3)]">
        {[track.default ? "Default" : null, track.forced ? "Forced" : null]
          .filter(Boolean)
          .join(", ") || "—"}
      </td>
      <td className="min-w-[16rem] px-3 py-2 text-xs leading-5 text-[var(--mm-text2)]">
        <ul className="list-disc space-y-1 pl-4">
          {track.reasons.map((reason, index) => (
            <li key={index}>{reason}</li>
          ))}
        </ul>
      </td>
    </tr>
  );
}

function PreviewResults({ result }: { result: ProcessingRulesPreviewResult }) {
  const sizeText = formatBytes(result.estimated_size_reduction_bytes);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span
          className={
            result.remux_required
              ? "rounded-full border border-amber-400/40 bg-amber-400/10 px-2.5 py-1 font-semibold text-amber-300"
              : "rounded-full border border-emerald-400/40 bg-emerald-400/10 px-2.5 py-1 font-semibold text-emerald-300"
          }
        >
          {result.remux_required
            ? "A remux would run"
            : "Already matches — no remux needed"}
        </span>
        {sizeText ? (
          <span className="text-[var(--mm-text3)]">
            Estimated size change: about {sizeText} smaller (estimate only)
          </span>
        ) : null}
      </div>

      <div className="w-full min-w-0 overflow-x-auto rounded border border-[var(--mm-border)]">
        <table className="w-full min-w-[52rem] text-left text-sm">
          <caption className="sr-only">
            Per-track plan for the previewed file
          </caption>
          <thead className="bg-black/20 text-[var(--mm-text2)]">
            <tr>
              <th scope="col" className="px-3 py-2 font-medium">
                #
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Type
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Codec
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Language
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Title
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Channels
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Action
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Flags
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Reasons
              </th>
            </tr>
          </thead>
          <tbody>
            {result.tracks.map((track) => (
              <TrackRow key={track.index} track={track} />
            ))}
          </tbody>
        </table>
      </div>

      {result.original_language ? (
        <p className="text-xs leading-5 text-[var(--mm-text3)]">
          Original language: {result.original_language.note}
        </p>
      ) : null}

      {result.metadata_notes.length > 0 ? (
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
            Container changes
          </h4>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-xs leading-5 text-[var(--mm-text2)]">
            {result.metadata_notes.map((note, index) => (
              <li key={index}>{note}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {result.notes.length > 0 ? (
        <details className="text-xs leading-5 text-[var(--mm-text2)]">
          <summary className="cursor-pointer font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
            Full plan notes ({result.notes.length})
          </summary>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {result.notes.map((note, index) => (
              <li key={index}>{note}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}

export function ProcessingRulesPreviewPanel({
  rules,
  disabled,
}: {
  /** The rules editor's current draft, saved or not \u2014 whatever the operator is looking at now. */
  rules: ProcessingRuleSetWrite | null;
  disabled?: boolean;
}) {
  const libraries = useProcessingLibrariesQuery();
  const preview = useProcessingRulesPreview();
  const [open, setOpen] = useState(false);
  const [libraryId, setLibraryId] = useState<number | "">("");
  const [pathMode, setPathMode] = useState<"library" | "anywhere">("library");
  const [relativePath, setRelativePath] = useState("");
  const [folder, setFolder] = useState("");
  const [fileName, setFileName] = useState("");
  const [result, setResult] = useState<ProcessingRulesPreviewResult | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const headingId = useId();

  useEffect(() => {
    if (libraryId !== "" || !libraries.data?.length) return;
    setLibraryId(libraries.data[0].id);
  }, [libraries.data, libraryId]);

  const absolutePath =
    pathMode === "anywhere" ? joinPath(folder, fileName) : "";
  const hasPath =
    pathMode === "library"
      ? relativePath.trim().length > 0
      : Boolean(absolutePath);

  const runPreview = () => {
    if (!open || !hasPath || libraryId === "") return;
    setError(null);
    preview.mutate(
      {
        libraryId,
        relativePath: pathMode === "library" ? relativePath.trim() : undefined,
        absolutePath: pathMode === "anywhere" ? absolutePath : undefined,
        rules: rules ?? undefined,
      },
      {
        onSuccess: (data) => setResult(data),
        onError: (err) => {
          setResult(null);
          setError(errorText(err, "That file could not be previewed."));
        },
      },
    );
  };

  // Re-run on every debounced rule edit, and whenever the chosen path or library changes, so the
  // panel always reflects what is on screen right now \u2014 saved or not.
  useEffect(() => {
    if (!open || !hasPath || libraryId === "") return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(runPreview, RERUN_DEBOUNCE_MS);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, libraryId, pathMode, relativePath, absolutePath, rules]);

  if (!open) {
    return (
      <section className="rounded-xl border border-[var(--mm-border)] bg-[var(--mm-surface2)] p-4 sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="font-semibold text-[var(--mm-text1)]">
              Try on a file
            </h3>
            <p className="mt-1 text-xs leading-5 text-[var(--mm-text3)]">
              See exactly what these rules would keep or drop on a real file —
              nothing is processed or queued.
            </p>
          </div>
          <button
            type="button"
            className={mmActionButtonClass({
              variant: "secondary",
              disabled,
            })}
            disabled={disabled}
            onClick={() => setOpen(true)}
          >
            Try on a file
          </button>
        </div>
      </section>
    );
  }

  return (
    <section
      className="space-y-4 rounded-xl border border-[var(--mm-border)] bg-[var(--mm-surface2)] p-4 sm:p-5"
      aria-labelledby={headingId}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 id={headingId} className="font-semibold text-[var(--mm-text1)]">
            Try on a file
          </h3>
          <p className="mt-1 text-xs leading-5 text-[var(--mm-text3)]">
            Read-only: this never processes, queues, or saves anything. It
            re-runs a moment after you stop editing the rules above.
          </p>
        </div>
        <button
          type="button"
          className={mmActionButtonClass({ variant: "tertiary" })}
          onClick={() => setOpen(false)}
        >
          Close
        </button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="text-[var(--mm-text2)]">Library</span>
          <select
            className={mmSelectFieldClass}
            value={libraryId}
            onChange={(event) => setLibraryId(Number(event.target.value))}
          >
            {(libraries.data ?? []).map((library) => (
              <option key={library.id} value={library.id}>
                {library.name}
              </option>
            ))}
          </select>
          <span className="mt-1 block text-xs text-[var(--mm-text3)]">
            Decides which watched/output folders a relative path may resolve
            against.
          </span>
        </label>

        <label className="block text-sm">
          <span className="text-[var(--mm-text2)]">Where is the file?</span>
          <select
            className={mmSelectFieldClass}
            value={pathMode}
            onChange={(event) =>
              setPathMode(
                event.target.value === "anywhere" ? "anywhere" : "library",
              )
            }
          >
            <option value="library">
              Inside the library&apos;s watched or output folder
            </option>
            <option value="anywhere">Anywhere on this machine</option>
          </select>
        </label>
      </div>

      {pathMode === "library" ? (
        <label className="block text-sm">
          <span className="text-[var(--mm-text2)]">
            Path within the watched or output folder
          </span>
          <input
            className={mmEditableTextFieldClass}
            value={relativePath}
            placeholder="Movie (2020)/Movie.mkv"
            onChange={(event) => setRelativePath(event.target.value)}
          />
        </label>
      ) : (
        <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
          <label className="block text-sm">
            <span className="text-[var(--mm-text2)]">Folder</span>
            <input
              className={mmEditableTextFieldClass}
              value={folder}
              placeholder={
                navigator.platform.toLowerCase().includes("win")
                  ? String.raw`X:\Media\Movies\Movie (2020)`
                  : "/media/movies/Movie (2020)"
              }
              onChange={(event) => setFolder(event.target.value)}
            />
          </label>
          <ServerFolderPickerButton
            title="Choose the file's folder"
            value={folder}
            onSelect={setFolder}
          />
          <label className="block text-sm sm:col-span-2">
            <span className="text-[var(--mm-text2)]">File name</span>
            <input
              className={mmEditableTextFieldClass}
              value={fileName}
              placeholder="Movie.mkv"
              onChange={(event) => setFileName(event.target.value)}
            />
          </label>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className={mmActionButtonClass({
            variant: "primary",
            disabled: !hasPath || libraryId === "" || preview.isPending,
          })}
          disabled={!hasPath || libraryId === "" || preview.isPending}
          onClick={runPreview}
        >
          {preview.isPending ? "Checking…" : "Preview"}
        </button>
        {preview.isPending ? (
          <span className="text-xs text-[var(--mm-text3)]" role="status">
            Reading the file and running the rules…
          </span>
        ) : null}
      </div>

      <div aria-live="polite">
        {error ? (
          <p
            role="alert"
            className="rounded border border-red-400/40 bg-red-400/10 px-3 py-2 text-sm text-red-200"
          >
            {error}
          </p>
        ) : null}
        {!error && result ? <PreviewResults result={result} /> : null}
      </div>
    </section>
  );
}
