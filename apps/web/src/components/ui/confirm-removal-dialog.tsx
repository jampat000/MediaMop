/**
 * The confirmation step in front of an irreversible "Remove" (#599 follow-up).
 *
 * Two Settings buttons — Remove on a media manager connection, and Remove on a notification
 * channel — used to delete on the first click. Nothing asked, nothing to undo. Layout was doing
 * the safety work: the media-manager cards were kept apart so it stayed obvious which Remove
 * belonged to which connection. That is not where a safety property should live, so it moves here.
 *
 * The frame is the one the app already uses for irreversible actions
 * (`LibraryRemovalConfirmationDialog`, `activity-history-dialogs`): same overlay, same card, same
 * Cancel-then-confirm button order. What it adds on top is the keyboard behaviour the slide-over
 * panels already have (`file-story-panel`, `choose-tracks-panel`): focus moves in on open and goes
 * back to whatever opened it on close, and Escape cancels.
 *
 * Focus lands on the cancel button, never on the destructive one, so Enter on a freshly opened
 * dialog keeps the thing rather than deleting it.
 *
 * `title` must name the item being removed. "Remove this connection?" is useless with three
 * connections on screen — naming the wrong one is exactly the failure this dialog exists to stop.
 */

import { useEffect, useId, useRef } from "react";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";

export function ConfirmRemovalDialog({
  title,
  description,
  confirmLabel,
  cancelLabel = "Keep it",
  busy,
  busyLabel = "Removing…",
  error,
  testId,
  onCancel,
  onConfirm,
}: {
  /** Names the item, e.g. "Remove Deluno?". */
  title: string;
  /** What removing it actually does, and that it cannot be undone. */
  description: React.ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  busy: boolean;
  busyLabel?: string;
  error: string | null;
  testId: string;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const titleId = useId();
  const descriptionId = useId();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const returnFocusTo = useRef<Element | null>(null);

  // Focus the safe choice on open, and hand focus back to the Remove button on close.
  useEffect(() => {
    returnFocusTo.current = document.activeElement;
    cancelRef.current?.focus();
    return () => {
      const target = returnFocusTo.current;
      if (target instanceof HTMLElement && target.isConnected) target.focus();
    };
  }, []);

  // Escape cancels — but not mid-request, for the same reason the cancel button is disabled then.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onCancel();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [busy, onCancel]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
      data-testid={testId}
    >
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-4 shadow-xl">
        <h3
          id={titleId}
          className="text-base font-semibold text-[var(--mm-text1)]"
        >
          {title}
        </h3>
        <div
          id={descriptionId}
          className="mt-2 space-y-2 text-sm leading-6 text-[var(--mm-text2)]"
        >
          {description}
        </div>
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
            ref={cancelRef}
            data-testid={`${testId}-cancel`}
            className={mmActionButtonClass({ variant: "secondary" })}
            onClick={onCancel}
            disabled={busy}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            data-testid={`${testId}-confirm`}
            className={mmActionButtonClass({
              variant: "primary",
              disabled: busy,
            })}
            disabled={busy}
            onClick={onConfirm}
          >
            {busy ? busyLabel : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
