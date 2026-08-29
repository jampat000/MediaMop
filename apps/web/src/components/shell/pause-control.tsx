import { useState } from "react";

import { useMeQuery } from "../../lib/auth/queries";
import {
  useSaveSuitePause,
  useSuitePauseQuery,
} from "../../lib/suite/pause-queries";

/** Minutes offered for a pause that lifts itself. */
const DURATIONS: { label: string; minutes: number | null }[] = [
  { label: "30 minutes", minutes: 30 },
  { label: "2 hours", minutes: 120 },
  { label: "8 hours", minutes: 480 },
  { label: "Until I resume", minutes: null },
];

function canEdit(role: string | undefined): boolean {
  return role === "admin" || role === "operator";
}

/**
 * Pause processing, from anywhere in the app.
 *
 * It lives in the shell rather than on the Refiner page because the reason to reach for
 * it — the machine is busy and you want it back — has nothing to do with which screen
 * you happen to be on.
 */
export function PauseControl() {
  const me = useMeQuery();
  const pause = useSuitePauseQuery();
  const save = useSaveSuitePause();
  const [open, setOpen] = useState(false);

  const editable = canEdit(me.data?.role);
  const state = pause.data;
  if (!state) return null;

  const resume = () =>
    save.mutate({
      paused: false,
      scan_while_paused: state.scan_while_paused,
    });

  if (state.paused) {
    return (
      <div className="mm-pause-control" data-testid="pause-control">
        <span className="mm-pause-badge" data-testid="pause-badge">
          Paused
        </span>
        {/* The reason carries the expiry, so an operator never has to guess how long. */}
        <span className="mm-pause-reason" data-testid="pause-reason">
          {state.reason}
        </span>
        {editable ? (
          <button
            type="button"
            className="mm-theme-toggle"
            data-testid="pause-resume"
            disabled={save.isPending}
            onClick={resume}
          >
            {save.isPending ? "Resuming…" : "Resume"}
          </button>
        ) : null}
      </div>
    );
  }

  if (!editable) return null;

  return (
    <div className="mm-pause-control" data-testid="pause-control">
      <button
        type="button"
        className="mm-theme-toggle"
        data-testid="pause-open"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        Pause processing
      </button>
      {open ? (
        <div className="mm-pause-menu" data-testid="pause-menu">
          {DURATIONS.map((d) => (
            <button
              key={d.label}
              type="button"
              className="mm-theme-toggle"
              data-testid={`pause-for-${d.minutes ?? "indefinite"}`}
              disabled={save.isPending}
              onClick={() => {
                save.mutate({
                  paused: true,
                  pause_for_minutes: d.minutes,
                  scan_while_paused: state.scan_while_paused,
                });
                setOpen(false);
              }}
            >
              {d.label}
            </button>
          ))}
          <label className="mm-pause-scan-toggle">
            <input
              type="checkbox"
              data-testid="pause-scan-while-paused"
              checked={state.scan_while_paused}
              onChange={(e) =>
                save.mutate({
                  paused: state.paused,
                  scan_while_paused: e.target.checked,
                })
              }
            />
            Keep looking for new files while paused
          </label>
          {/* Said out loud, because the assumption otherwise is that work stops dead. */}
          <p className="mm-pause-policy" data-testid="pause-policy">
            {state.in_flight_policy}
          </p>
        </div>
      ) : null}
    </div>
  );
}
