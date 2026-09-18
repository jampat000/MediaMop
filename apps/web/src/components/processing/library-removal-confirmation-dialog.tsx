/**
 * The #505 point 5 final-removal warning, shared by Clean and by turning the schedule on for the first time.
 * The wording is exact: "N files, M tracks will be removed. Removed tracks are gone for good; getting one
 * back means downloading the title again." plus the size saved.
 */
import { formatBytes } from "../../lib/processing/library-api";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";

export function LibraryRemovalConfirmationDialog({
  filesCount,
  tracksCount,
  estimatedBytesSaved,
  busy,
  error,
  /**
   * Per-file or summarised risk notes shown between the size line and the buttons — the seeding/re-download
   * warnings #508 (`LibraryCleanPreflight`) will supply once that branch lands. Empty by default: #505 has
   * nothing of its own to show here yet, but the dialog already renders whatever it is given.
   */
  warnings = [],
  confirmLabel = "Clean",
  onCancel,
  onConfirm,
}: {
  filesCount: number;
  tracksCount: number;
  estimatedBytesSaved: number;
  busy: boolean;
  error: string | null;
  warnings?: string[];
  confirmLabel?: string;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="library-removal-confirmation-title"
      data-testid="library-removal-confirmation-dialog"
    >
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-4 shadow-xl">
        <h3
          id="library-removal-confirmation-title"
          className="text-base font-semibold text-[var(--mm-text1)]"
        >
          Removing tracks cannot be undone
        </h3>
        <p
          className="mt-3 text-sm leading-6 text-[var(--mm-text1)]"
          data-testid="library-removal-confirmation-detail"
        >
          {filesCount} files, {tracksCount} tracks will be removed. Removed
          tracks are gone for good; getting one back means downloading the title
          again.
        </p>
        <p className="mt-2 text-sm text-[var(--mm-text2)]">
          Estimated size saved: {formatBytes(estimatedBytesSaved)}
        </p>
        {warnings.length > 0 ? (
          <ul
            className="mt-3 list-inside list-disc space-y-1 text-sm text-[var(--mm-status-warning-text)]"
            data-testid="library-removal-confirmation-warnings"
          >
            {warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        ) : null}
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
            Cancel
          </button>
          <button
            type="button"
            className={mmActionButtonClass({
              variant: "primary",
              disabled: busy,
            })}
            disabled={busy}
            onClick={onConfirm}
          >
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
