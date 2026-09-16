/**
 * What happened to one file, told in plain language (#468).
 *
 * Opens as a slide-over so an operator never loses their place in a long list: close it and they
 * are exactly where they were. The story itself is written by the backend from the stored pass
 * record, so this component only presents it — the raw record stays one click away for anyone who
 * wants the technical detail, but it is never the first thing shown.
 */

import { useEffect, useId, useRef } from "react";
import { DirectPlayLine } from "./direct-play-line";
import type {
  RefinerDirectPlay,
  RefinerFileLog,
  RefinerFileStoryStep,
} from "../../lib/refiner/files-api";

const TONE_CLASS: Record<string, string> = {
  good: "mm-story-step--good",
  warn: "mm-story-step--warn",
  bad: "mm-story-step--bad",
  neutral: "",
};

function formatWhen(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

function Step({ step }: { step: RefinerFileStoryStep }): React.ReactElement {
  return (
    <li className={`mm-story-step ${TONE_CLASS[step.tone] ?? ""}`}>
      <p className="mm-story-step__heading">{step.heading}</p>
      <p className="mm-story-step__sentence">{step.sentence}</p>
    </li>
  );
}

export interface FileStoryPanelProps {
  open: boolean;
  fileName: string;
  /** Which of the operator's devices will play the file directly. Information only. */
  directPlay?: RefinerDirectPlay[];
  log: RefinerFileLog | undefined;
  loading: boolean;
  error: string | null;
  onClose: () => void;
}

export function FileStoryPanel({
  open,
  fileName,
  directPlay = [],
  log,
  loading,
  error,
  onClose,
}: FileStoryPanelProps): React.ReactElement | null {
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const returnFocusTo = useRef<Element | null>(null);

  // Move focus into the panel when it opens, and give it back to whatever opened it on close.
  useEffect(() => {
    if (!open) return undefined;
    returnFocusTo.current = document.activeElement;
    panelRef.current?.focus();
    return () => {
      const target = returnFocusTo.current;
      if (target instanceof HTMLElement) target.focus();
    };
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const retention =
    log && log.retention_days > 0
      ? `MediaMop keeps these records for ${log.retention_days} days.`
      : log
        ? "MediaMop keeps these records until you remove them."
        : null;

  return (
    <div className="mm-story-layer">
      <button
        type="button"
        className="mm-story-backdrop"
        aria-label="Close file history"
        onClick={onClose}
      />
      <div
        ref={panelRef}
        className="mm-story-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <header className="mm-story-panel__head">
          <div className="mm-story-panel__titles">
            <p className="mm-story-panel__eyebrow">
              What happened to this file
            </p>
            <h2 id={titleId} className="mm-story-panel__title" title={fileName}>
              {fileName}
            </h2>
          </div>
          <button
            type="button"
            className="mm-story-panel__close"
            onClick={onClose}
            aria-label="Close"
          >
            ×
          </button>
        </header>

        <div className="mm-story-panel__body">
          <DirectPlayLine
            directPlay={directPlay}
            full
            testId="file-story-direct-play"
          />
          {loading ? (
            <p className="mm-story-panel__note">Reading the record…</p>
          ) : error ? (
            <p
              className="mm-story-panel__note mm-status-text--failed"
              role="alert"
            >
              {error}
            </p>
          ) : !log || log.entries.length === 0 ? (
            <p className="mm-story-panel__note">
              MediaMop has not worked on this file yet, so there is nothing to
              tell. Its story starts the first time it is processed.
            </p>
          ) : (
            log.entries.map((entry) => (
              <section key={entry.id} className="mm-story-pass">
                <h3 className="mm-story-pass__when">
                  {formatWhen(entry.recorded_at)}
                </h3>
                {entry.story.length > 0 ? (
                  <ol className="mm-story-steps">
                    {entry.story.map((step, index) => (
                      <Step key={`${entry.id}-${index}`} step={step} />
                    ))}
                  </ol>
                ) : (
                  <p className="mm-story-panel__note">{entry.title}</p>
                )}
                <details className="mm-story-pass__detail">
                  <summary>Show the technical detail</summary>
                  <pre>{JSON.stringify(entry.detail, null, 2)}</pre>
                </details>
              </section>
            ))
          )}
          {retention ? (
            <p className="mm-story-panel__retention">{retention}</p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
