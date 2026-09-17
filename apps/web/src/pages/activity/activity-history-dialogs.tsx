/**
 * The two irreversible Activity actions (#469). Each confirmation quotes the server's own
 * counts, so the operator sees exactly what will be removed before anything is.
 */

import { useState } from "react";
import type { ActivityFileHistoryPreview } from "../../lib/api/types";
import type { SuiteOperationalHistoryResetOut } from "../../lib/suite/types";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

function DialogFrame({
  titleId,
  title,
  testId,
  children,
}: {
  titleId: string;
  title: string;
  testId: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      data-testid={testId}
    >
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-4 shadow-xl">
        <h3
          id={titleId}
          className="text-base font-semibold text-[var(--mm-text1)]"
        >
          {title}
        </h3>
        {children}
      </div>
    </div>
  );
}

export function RemoveFileHistoryDialog({
  preview,
  busy,
  error,
  onCancel,
  onConfirm,
}: {
  preview: ActivityFileHistoryPreview;
  busy: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const nothing =
    preview.activity_events === 0 && preview.processing_records === 0;
  return (
    <DialogFrame
      titleId="activity-remove-file-history-title"
      title="Remove this file's history?"
      testId="activity-remove-file-history-dialog"
    >
      <p className="mt-2 break-words text-sm leading-6 text-[var(--mm-text2)] [overflow-wrap:anywhere]">
        {preview.message}
      </p>
      <ul className="mt-3 list-inside list-disc space-y-1 text-sm text-[var(--mm-text1)]">
        <li>
          {plural(preview.activity_events, "Activity event", "Activity events")}
        </li>
        <li>
          {plural(
            preview.processing_records,
            "processing record",
            "processing records",
          )}
        </li>
      </ul>
      <p className="mt-3 text-sm text-[var(--mm-text2)]">
        This cannot be undone. No media file is touched.
      </p>
      {error ? (
        <p
          className="mt-3 text-sm text-[var(--mm-status-failed-text)]"
          role="alert"
        >
          {error}
        </p>
      ) : null}
      <div className="mt-4 flex flex-wrap justify-end gap-2">
        <button
          type="button"
          className={mmActionButtonClass({ variant: "secondary" })}
          onClick={onCancel}
          disabled={busy}
        >
          Keep it
        </button>
        <button
          type="button"
          className={mmActionButtonClass({
            variant: "primary",
            disabled: busy || nothing,
          })}
          disabled={busy || nothing}
          onClick={onConfirm}
        >
          {busy ? "Removing…" : "Remove history"}
        </button>
      </div>
    </DialogFrame>
  );
}

export function ClearAllHistoryDialog({
  preview,
  busy,
  error,
  onCancel,
  onConfirm,
}: {
  preview: SuiteOperationalHistoryResetOut;
  busy: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: (confirm: string) => void;
}) {
  const [typed, setTyped] = useState("");
  const ready = typed.trim().toUpperCase() === "RESET";
  return (
    <DialogFrame
      titleId="activity-clear-all-history-title"
      title="Clear all history?"
      testId="activity-clear-all-history-dialog"
    >
      <p className="mt-2 text-sm text-[var(--mm-text2)]">
        This permanently removes:
      </p>
      <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-[var(--mm-text1)]">
        <li>
          {plural(
            preview.activity_events_deleted,
            "Activity event",
            "Activity events",
          )}
        </li>
        <li>
          {plural(
            preview.refiner_jobs_deleted,
            "finished Refiner job",
            "finished Refiner jobs",
          )}
        </li>
      </ul>
      <p className="mt-3 text-sm leading-6 text-[var(--mm-text2)]">
        Queued and running work is kept, and so are all settings. No media file
        is touched. This cannot be undone.
      </p>
      <label className="mt-3 block text-sm text-[var(--mm-text2)]">
        <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-[var(--mm-text3)]">
          Type RESET to confirm
        </span>
        <input
          type="text"
          className="mm-input w-full"
          value={typed}
          disabled={busy}
          onChange={(e) => setTyped(e.target.value)}
        />
      </label>
      {error ? (
        <p
          className="mt-3 text-sm text-[var(--mm-status-failed-text)]"
          role="alert"
        >
          {error}
        </p>
      ) : null}
      <div className="mt-4 flex flex-wrap justify-end gap-2">
        <button
          type="button"
          className={mmActionButtonClass({ variant: "secondary" })}
          onClick={onCancel}
          disabled={busy}
        >
          Keep history
        </button>
        <button
          type="button"
          className={mmActionButtonClass({
            variant: "primary",
            disabled: busy || !ready,
          })}
          disabled={busy || !ready}
          onClick={() => onConfirm(typed.trim())}
        >
          {busy ? "Clearing…" : "Clear all history"}
        </button>
      </div>
    </DialogFrame>
  );
}
