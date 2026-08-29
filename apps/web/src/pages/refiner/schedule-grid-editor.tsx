import { useCallback, useState } from "react";

const SLOTS_PER_HOUR = 4;
const SLOTS_PER_DAY = 24 * SLOTS_PER_HOUR;
const SLOTS_PER_WEEK = 7 * SLOTS_PER_DAY;
/** Monday first, matching the backend's weekday convention. */
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function emptyGrid(): string {
  return "";
}

function normalized(grid: string): string {
  if (grid.length === SLOTS_PER_WEEK && !/[^01]/.test(grid)) return grid;
  // Anything unusable is drawn as "no restriction", which is what the backend does with
  // it too — a display that invented a schedule would be worse than one that shows none.
  return "1".repeat(SLOTS_PER_WEEK);
}

function withSlot(grid: string, index: number, on: boolean): string {
  const base = normalized(grid);
  return `${base.slice(0, index)}${on ? "1" : "0"}${base.slice(index + 1)}`;
}

function hourIsOn(grid: string, day: number, hour: number): boolean {
  const base = normalized(grid);
  const start = day * SLOTS_PER_DAY + hour * SLOTS_PER_HOUR;
  for (let i = 0; i < SLOTS_PER_HOUR; i += 1) {
    if (base[start + i] === "1") return true;
  }
  return false;
}

function setHour(grid: string, day: number, hour: number, on: boolean): string {
  let next = normalized(grid);
  const start = day * SLOTS_PER_DAY + hour * SLOTS_PER_HOUR;
  for (let i = 0; i < SLOTS_PER_HOUR; i += 1) {
    next = withSlot(next, start + i, on);
  }
  return next;
}

export interface ScheduleGridEditorProps {
  value: string;
  onChange: (grid: string) => void;
  disabled?: boolean;
}

/**
 * A 7x24 schedule.
 *
 * The stored grid is quarter-hour resolution, but the *editor* works in whole hours:
 * 168 targets are usable with a mouse and 672 are not, and an hour toggle writes all
 * four of its quarters so nothing is lost in the round trip. Anyone needing a 15-minute
 * boundary can still set it through the API, which is the honest trade rather than
 * pretending the grid is hourly.
 */
export function ScheduleGridEditor({
  value,
  onChange,
  disabled = false,
}: ScheduleGridEditorProps) {
  const [painting, setPainting] = useState<boolean | null>(null);

  const toggle = useCallback(
    (day: number, hour: number, on: boolean) => {
      if (disabled) return;
      onChange(setHour(value, day, hour, on));
    },
    [disabled, onChange, value],
  );

  const unrestricted = value.length !== SLOTS_PER_WEEK;

  return (
    <div className="mm-schedule-grid" data-testid="schedule-grid">
      <p className="text-xs text-[var(--mm-text3)]">
        {unrestricted
          ? "No schedule set — this library runs at any time. Select hours to limit it."
          : "Selected hours are when MediaMop may start work. Work already running finishes."}
      </p>
      <div
        className="mm-schedule-grid-body"
        onPointerUp={() => setPainting(null)}
        onPointerLeave={() => setPainting(null)}
      >
        <div className="mm-schedule-grid-hours" aria-hidden="true">
          <span />
          {Array.from({ length: 24 }, (_, hour) => (
            <span key={hour}>{hour % 6 === 0 ? hour : ""}</span>
          ))}
        </div>
        {DAYS.map((label, day) => (
          <div className="mm-schedule-grid-row" key={label}>
            <span className="mm-schedule-grid-day">{label}</span>
            {Array.from({ length: 24 }, (_, hour) => {
              const on = hourIsOn(value, day, hour);
              return (
                <button
                  key={hour}
                  type="button"
                  disabled={disabled}
                  className={
                    on
                      ? "mm-schedule-cell mm-schedule-cell-on"
                      : "mm-schedule-cell"
                  }
                  aria-pressed={on}
                  aria-label={`${label} ${String(hour).padStart(2, "0")}:00`}
                  data-testid={`schedule-cell-${day}-${hour}`}
                  onPointerDown={() => {
                    setPainting(!on);
                    toggle(day, hour, !on);
                  }}
                  // Dragging across the grid is how anyone actually draws a window;
                  // clicking 40 cells one at a time is not a schedule editor.
                  onPointerEnter={() => {
                    if (painting !== null) toggle(day, hour, painting);
                  }}
                />
              );
            })}
          </div>
        ))}
      </div>
      <div className="mm-schedule-grid-actions">
        <button
          type="button"
          disabled={disabled}
          className="mm-theme-toggle"
          data-testid="schedule-clear"
          onClick={() => onChange(emptyGrid())}
        >
          Any time
        </button>
        <button
          type="button"
          disabled={disabled}
          className="mm-theme-toggle"
          data-testid="schedule-none"
          onClick={() => onChange("0".repeat(SLOTS_PER_WEEK))}
        >
          Clear all
        </button>
      </div>
    </div>
  );
}
