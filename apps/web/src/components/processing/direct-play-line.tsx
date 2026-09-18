/**
 * The Direct Play badge (#467): which of the operator's devices will play a file without the
 * media server converting it, and why not.
 *
 * Information only. It never changes what Weir does to a file, so nothing here offers to
 * fix or convert anything. Verdicts are carried in words (visible or screen-reader text), never
 * by symbol or colour alone.
 */

import { Fragment } from "react";
import type {
  ProcessingDirectPlay,
  ProcessingDirectPlayVerdict,
} from "../../lib/processing/files-api";

const SYMBOL: Record<ProcessingDirectPlayVerdict, string> = {
  yes: "✓",
  no: "✗",
  maybe: "?",
  unknown: "",
};

const WORD: Record<ProcessingDirectPlayVerdict, string> = {
  yes: "yes",
  no: "no",
  maybe: "maybe",
  unknown: "not measured yet",
};

const SENTENCE: Record<
  Exclude<ProcessingDirectPlayVerdict, "unknown">,
  string
> = {
  yes: "plays it directly",
  no: "cannot play it directly, so the media server will convert it",
  maybe: "may not play it directly, so the media server may convert it",
};

/** The first reason, shortened for the one-line view. "cannot play DTS audio" reads "DTS audio". */
function shortReason(entry: ProcessingDirectPlay): string | null {
  if (entry.verdict === "unknown") return WORD.unknown;
  const first = entry.reasons[0];
  if (!first) return null;
  const shown =
    entry.verdict === "no" ? first.replace(/^cannot play\s+/i, "") : first;
  const more = entry.reasons.length - 1;
  return more > 0 ? `${shown}, +${more} more` : shown;
}

function fullSentence(entry: ProcessingDirectPlay): string {
  if (entry.verdict === "unknown") {
    return `${entry.device_name}: not measured yet, so Weir cannot say.`;
  }
  const lead = `${entry.device_name} ${SENTENCE[entry.verdict]}`;
  return entry.reasons.length
    ? `${lead}: ${entry.reasons.join("; ")}.`
    : `${lead}.`;
}

function DeviceVerdict({
  entry,
}: {
  entry: ProcessingDirectPlay;
}): React.ReactElement {
  const symbol = SYMBOL[entry.verdict];
  const reason = shortReason(entry);
  return (
    <span
      className={`mm-direct-play__device mm-direct-play__device--${entry.verdict}`}
      title={fullSentence(entry)}
    >
      {entry.device_name}
      {symbol ? (
        <>
          <span className="mm-direct-play__mark" aria-hidden="true">
            {" "}
            {symbol}
          </span>
          <span className="sr-only"> {WORD[entry.verdict]}</span>
        </>
      ) : null}
      {reason ? ` (${reason})` : null}
    </span>
  );
}

export function DirectPlayLine({
  directPlay,
  full = false,
  testId,
}: {
  directPlay: ProcessingDirectPlay[];
  /** Lists every device with its full reasons, for a detail view rather than a list row. */
  full?: boolean;
  testId?: string;
}): React.ReactElement | null {
  if (directPlay.length === 0) return null;

  if (full) {
    return (
      <section
        className="mm-direct-play mm-direct-play--full"
        data-testid={testId}
      >
        <h3 className="mm-direct-play__heading">Direct Play on your devices</h3>
        <ul className="mm-direct-play__reasons">
          {directPlay.map((entry) => (
            <li key={entry.device_id}>{fullSentence(entry)}</li>
          ))}
        </ul>
        <p className="mm-direct-play__note">
          Information only. Weir never changes a file because of this.
        </p>
      </section>
    );
  }

  const explained = directPlay.filter((entry) => entry.reasons.length > 0);
  return (
    <div className="mm-direct-play" data-testid={testId}>
      <span className="mm-direct-play__label">Direct Play:</span>{" "}
      {directPlay.map((entry, index) => (
        <Fragment key={entry.device_id}>
          {index > 0 ? <span aria-hidden="true"> · </span> : null}
          <DeviceVerdict entry={entry} />
        </Fragment>
      ))}
      {explained.length > 0 ? (
        <details className="mm-direct-play__why">
          <summary>Why</summary>
          <ul className="mm-direct-play__reasons">
            {explained.map((entry) => (
              <li key={entry.device_id}>{fullSentence(entry)}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}
