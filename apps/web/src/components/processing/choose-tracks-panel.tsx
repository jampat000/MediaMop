/**
 * "Choose tracks by hand" (issue #501): let an operator override the automatic rules for one held
 * file by picking exactly which video, audio and subtitle tracks to keep, their default/forced
 * flags and their order, then queue a remux pass built straight from that choice.
 *
 * Opens as the same slide-over shell as the processing-record panel (file-story-panel.tsx), so an
 * operator never loses their place in the Files list. Reordering uses plain up/down buttons rather
 * than drag-and-drop, so it works the same with a keyboard, a screen reader, or a mouse.
 */

import { useEffect, useId, useRef, useState } from "react";

import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import type {
  ProcessingFileTrack,
  ProcessingFileTracks,
  ProcessingManualPlanChoice,
} from "../../lib/processing/files-api";
import { plural } from "../../lib/ui/mm-plural";

type SelectableType = "video" | "audio" | "subtitle";

function isSelectable(
  type: ProcessingFileTrack["type"],
): type is SelectableType {
  return type === "video" || type === "audio" || type === "subtitle";
}

interface RowState {
  keep: boolean;
  default: boolean;
  forced: boolean;
}

/** Seeded from what the saved rules would have done, so the starting point is never empty. */
function initialRowState(track: ProcessingFileTrack): RowState {
  return {
    keep: track.rule_would_keep,
    default: track.rule_would_keep && track.default,
    forced: track.rule_would_keep && track.forced,
  };
}

function trackLabel(track: ProcessingFileTrack): string {
  const bits: string[] = [];
  if (track.language) bits.push(track.language);
  if (track.codec) bits.push(track.codec);
  if (track.channels) bits.push(`${track.channels} ch`);
  if (track.title) bits.push(`"${track.title}"`);
  const detail = bits.length > 0 ? bits.join(" · ") : "no tags";
  return `#${track.index} ${track.type} (${detail})`;
}

export interface ChooseTracksPanelProps {
  open: boolean;
  fileName: string;
  tracks: ProcessingFileTracks | undefined;
  loading: boolean;
  loadError: string | null;
  submitting: boolean;
  submitError: string | null;
  onClose: () => void;
  onSubmit: (choice: ProcessingManualPlanChoice) => void;
}

export function ChooseTracksPanel({
  open,
  fileName,
  tracks,
  loading,
  loadError,
  submitting,
  submitError,
  onClose,
  onSubmit,
}: ChooseTracksPanelProps): React.ReactElement | null {
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const returnFocusTo = useRef<Element | null>(null);
  const [rows, setRows] = useState<Record<number, RowState>>({});
  const [order, setOrder] = useState<number[]>([]);

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

  // Seed selection state from a fresh set of tracks: a new open, or a reload after "choose again".
  useEffect(() => {
    if (!tracks) return;
    const nextRows: Record<number, RowState> = {};
    const kept: number[] = [];
    for (const track of tracks.streams) {
      if (!isSelectable(track.type)) continue;
      const state = initialRowState(track);
      nextRows[track.index] = state;
      if (state.keep) kept.push(track.index);
    }
    setRows(nextRows);
    setOrder(kept);
  }, [tracks]);

  if (!open) return null;

  const selectable = (tracks?.streams ?? []).filter((track) =>
    isSelectable(track.type),
  );
  const other = (tracks?.streams ?? []).filter(
    (track) => !isSelectable(track.type),
  );

  const setKeep = (track: ProcessingFileTrack, keep: boolean) => {
    setRows((previous) => ({
      ...previous,
      [track.index]: { ...previous[track.index], keep },
    }));
    setOrder((previous) => {
      if (keep) {
        return previous.includes(track.index)
          ? previous
          : [...previous, track.index];
      }
      return previous.filter((index) => index !== track.index);
    });
  };

  const setDefault = (type: SelectableType, index: number) => {
    setRows((previous) => {
      const next = { ...previous };
      for (const track of selectable) {
        if (track.type !== type) continue;
        next[track.index] = {
          ...next[track.index],
          default: track.index === index,
        };
      }
      return next;
    });
  };

  const setForced = (index: number, forced: boolean) => {
    setRows((previous) => ({
      ...previous,
      [index]: { ...previous[index], forced },
    }));
  };

  const move = (index: number, direction: -1 | 1) => {
    setOrder((previous) => {
      const position = previous.indexOf(index);
      const target = position + direction;
      if (position < 0 || target < 0 || target >= previous.length) {
        return previous;
      }
      const next = [...previous];
      [next[position], next[target]] = [next[target], next[position]];
      return next;
    });
  };

  const keptTracks = order
    .map((index) => selectable.find((track) => track.index === index))
    .filter((track): track is ProcessingFileTrack => track !== undefined);
  const dropped = selectable.filter(
    (track) => !(rows[track.index]?.keep ?? false),
  );

  const keptVideoCount = keptTracks.filter(
    (track) => track.type === "video",
  ).length;
  const keptAudioCount = keptTracks.filter(
    (track) => track.type === "audio",
  ).length;
  const validationError =
    keptVideoCount === 0
      ? "Keep at least one video track."
      : keptAudioCount === 0
        ? "Keep at least one audio track."
        : null;

  const submit = () => {
    if (validationError) return;
    onSubmit({
      // Default and forced only mean anything for audio and subtitle tracks; a video track
      // always submits false for both, whatever its own disposition on the source said.
      keep: order.map((index) => {
        const type = selectable.find((track) => track.index === index)?.type;
        return {
          index,
          default: type === "video" ? false : (rows[index]?.default ?? false),
          forced: type === "video" ? false : (rows[index]?.forced ?? false),
        };
      }),
      order,
    });
  };

  return (
    <div className="mm-story-layer">
      <button
        type="button"
        className="mm-story-backdrop"
        aria-label="Close choose tracks"
        onClick={onClose}
      />
      <div
        ref={panelRef}
        className="mm-story-panel mm-tracks-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        data-testid="choose-tracks-panel"
      >
        <header className="mm-story-panel__head">
          <div className="mm-story-panel__titles">
            <p className="mm-story-panel__eyebrow">Choose tracks by hand</p>
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
          {loading ? (
            <p className="mm-story-panel__note">
              Reading a fresh probe of this file…
            </p>
          ) : loadError ? (
            <p
              className="mm-story-panel__note mm-status-text--failed"
              role="alert"
            >
              {loadError}
            </p>
          ) : !tracks ? null : (
            <>
              <p className="mm-story-panel__note">
                Weir just re-read this file&apos;s tracks. Choose what to keep,
                mark one default audio track and, if you want, one default
                subtitle track, then submit. Weir checks the file again right
                before running the pass, and will ask you to choose again if it
                changed since now.
              </p>

              <div className="mm-tracks-table-wrap">
                <table className="mm-tracks-table">
                  <thead>
                    <tr>
                      <th scope="col">Keep</th>
                      <th scope="col">Track</th>
                      <th scope="col">Default</th>
                      <th scope="col">Forced</th>
                      <th scope="col">What the saved rules would do</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectable.map((track) => {
                      const state = rows[track.index];
                      return (
                        <tr
                          key={track.index}
                          data-testid={`choose-tracks-row-${track.index}`}
                        >
                          <td>
                            <input
                              type="checkbox"
                              checked={state?.keep ?? false}
                              onChange={(e) => setKeep(track, e.target.checked)}
                              aria-label={`Keep ${trackLabel(track)}`}
                              data-testid={`choose-tracks-keep-${track.index}`}
                            />
                          </td>
                          <td className="mm-tracks-table__track">
                            {trackLabel(track)}
                          </td>
                          <td>
                            {track.type === "video" ? null : (
                              <input
                                type="radio"
                                name={`choose-tracks-default-${track.type}`}
                                checked={state?.default ?? false}
                                disabled={!(state?.keep ?? false)}
                                onChange={() =>
                                  setDefault(
                                    track.type as SelectableType,
                                    track.index,
                                  )
                                }
                                aria-label={`Make ${trackLabel(track)} the default ${track.type} track`}
                                data-testid={`choose-tracks-default-${track.index}`}
                              />
                            )}
                          </td>
                          <td>
                            {track.type === "subtitle" ? (
                              <input
                                type="checkbox"
                                checked={state?.forced ?? false}
                                disabled={!(state?.keep ?? false)}
                                onChange={(e) =>
                                  setForced(track.index, e.target.checked)
                                }
                                aria-label={`Mark ${trackLabel(track)} forced`}
                                data-testid={`choose-tracks-forced-${track.index}`}
                              />
                            ) : null}
                          </td>
                          <td className="mm-tracks-table__rule">
                            <strong>
                              {track.rule_would_keep
                                ? "Would keep"
                                : "Would remove"}
                            </strong>{" "}
                            — {track.rule_reason}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {other.length > 0 ? (
                <details className="mm-story-pass__detail">
                  <summary>
                    {plural(
                      other.length,
                      "embedded image or attachment stream",
                      "embedded image or attachment streams",
                    )}{" "}
                    not shown above — these are handled by the saved rules, not
                    by this choice
                  </summary>
                  <ul>
                    {other.map((track) => (
                      <li key={track.index}>
                        #{track.index} {track.type} —{" "}
                        {track.rule_would_keep ? "kept" : "removed"}:{" "}
                        {track.rule_reason}
                      </li>
                    ))}
                  </ul>
                </details>
              ) : null}

              <section className="mm-tracks-order" aria-label="Track order">
                <h3 className="mm-story-pass__when">Order</h3>
                {keptTracks.length === 0 ? (
                  <p className="mm-story-panel__note">Nothing is kept yet.</p>
                ) : (
                  <ol className="mm-tracks-order__list">
                    {keptTracks.map((track, position) => (
                      <li
                        key={track.index}
                        data-testid={`choose-tracks-order-${track.index}`}
                      >
                        <span>{trackLabel(track)}</span>
                        <span className="mm-tracks-order__buttons">
                          <button
                            type="button"
                            onClick={() => move(track.index, -1)}
                            disabled={position === 0}
                            aria-label={`Move ${trackLabel(track)} earlier`}
                            data-testid={`choose-tracks-move-up-${track.index}`}
                          >
                            ↑
                          </button>
                          <button
                            type="button"
                            onClick={() => move(track.index, 1)}
                            disabled={position === keptTracks.length - 1}
                            aria-label={`Move ${trackLabel(track)} later`}
                            data-testid={`choose-tracks-move-down-${track.index}`}
                          >
                            ↓
                          </button>
                        </span>
                      </li>
                    ))}
                  </ol>
                )}
              </section>

              <section
                className="mm-tracks-dropped"
                aria-label="Tracks that will be dropped"
              >
                <h3 className="mm-story-pass__when">Will be dropped</h3>
                {dropped.length === 0 ? (
                  <p className="mm-story-panel__note">
                    Nothing — every video, audio and subtitle track is kept.
                  </p>
                ) : (
                  <ul
                    className="mm-tracks-order__list"
                    data-testid="choose-tracks-dropped-list"
                  >
                    {dropped.map((track) => (
                      <li key={track.index}>{trackLabel(track)}</li>
                    ))}
                  </ul>
                )}
              </section>

              {validationError ? (
                <p
                  className="mm-story-panel__note mm-status-text--failed"
                  role="alert"
                >
                  {validationError}
                </p>
              ) : null}
              {submitError ? (
                <p
                  className="mm-story-panel__note mm-status-text--failed"
                  role="alert"
                  data-testid="choose-tracks-submit-error"
                >
                  {submitError}
                </p>
              ) : null}

              <div className="mm-tracks-footer">
                <button
                  type="button"
                  className={mmActionButtonClass({ variant: "tertiary" })}
                  onClick={onClose}
                  disabled={submitting}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className={mmActionButtonClass({
                    variant: "primary",
                    disabled: submitting || Boolean(validationError),
                  })}
                  onClick={submit}
                  disabled={submitting || Boolean(validationError)}
                  data-testid="choose-tracks-submit"
                >
                  {submitting ? "Queueing…" : "Queue this choice"}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
