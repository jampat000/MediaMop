/**
 * Shared weekday + time-window controls (*arr* search lanes, Refiner watched-folder schedules).
 * Persistence and semantics stay module-specific; this file is presentation only.
 */

import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";

/** Word-for-word match across Refiner, Pruner, and Subber schedule UIs. */
export const MM_SCHEDULE_TIME_WINDOW_HEADING = "Limit to these hours";
export const MM_SCHEDULE_TIME_WINDOW_HELPER =
  "When on, this only runs inside the hours and days you set below. Turn off to run at any time.";
export const MM_SCHEDULE_DAYS_HELPER =
  "Use a shortcut for common patterns, or tap days to turn them on or off. Every day means this window applies all week.";

export const SCHEDULE_WEEKDAY_TOKENS = [
  "Mon",
  "Tue",
  "Wed",
  "Thu",
  "Fri",
  "Sat",
  "Sun",
] as const;

export type ScheduleWeekdayToken = (typeof SCHEDULE_WEEKDAY_TOKENS)[number];

export function normalizeScheduleTimeForInput(hhmm: string): string {
  const t = hhmm.trim();
  const m = t.match(/^(\d{1,2}):(\d{2})$/);
  if (!m) {
    return "00:00";
  }
  const h = Math.min(23, Math.max(0, parseInt(m[1], 10)));
  const min = Math.min(59, Math.max(0, parseInt(m[2], 10)));
  return `${String(h).padStart(2, "0")}:${String(min).padStart(2, "0")}`;
}

export function daySelectionFromScheduleDaysCsv(
  csv: string,
): Set<ScheduleWeekdayToken> {
  const raw = csv.trim();
  if (!raw) {
    return new Set(SCHEDULE_WEEKDAY_TOKENS);
  }
  const next = new Set<ScheduleWeekdayToken>();
  for (const p of raw.split(",")) {
    const t = p.trim() as ScheduleWeekdayToken;
    if (SCHEDULE_WEEKDAY_TOKENS.includes(t)) {
      next.add(t);
    }
  }
  return next.size > 0 ? next : new Set(SCHEDULE_WEEKDAY_TOKENS);
}

export function scheduleCsvFromDaySelection(
  selected: Set<ScheduleWeekdayToken>,
): string {
  if (selected.size === 0 || selected.size === SCHEDULE_WEEKDAY_TOKENS.length) {
    return "";
  }
  return SCHEDULE_WEEKDAY_TOKENS.filter((d) => selected.has(d)).join(",");
}

export function MmScheduleDayChips({
  scheduleDaysCsv,
  disabled,
  onChangeCsv,
}: {
  scheduleDaysCsv: string;
  disabled: boolean;
  onChangeCsv: (csv: string) => void;
}) {
  const selected = daySelectionFromScheduleDaysCsv(scheduleDaysCsv);

  const toggle = (d: ScheduleWeekdayToken) => {
    const next = new Set(selected);
    if (next.has(d)) {
      next.delete(d);
    } else {
      next.add(d);
    }
    onChangeCsv(scheduleCsvFromDaySelection(next));
  };

  const preset = (days: ScheduleWeekdayToken[] | "all" | "clear") => {
    if (days === "all" || days === "clear") {
      onChangeCsv("");
      return;
    }
    onChangeCsv(scheduleCsvFromDaySelection(new Set(days)));
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1.5">
        {SCHEDULE_WEEKDAY_TOKENS.map((d) => {
          const on = selected.has(d);
          return (
            <button
              key={d}
              type="button"
              disabled={disabled}
              aria-pressed={on}
              onClick={() => toggle(d)}
              className={[
                "min-w-[2.75rem] rounded-md border px-2 py-1 text-xs font-medium transition-colors",
                on
                  ? "border-[rgba(212,175,55,0.45)] bg-[var(--mm-accent-soft)] text-[var(--mm-text1)]"
                  : "border-[var(--mm-border)] bg-transparent text-[var(--mm-text2)] hover:bg-[var(--mm-card-bg)]/60",
                disabled ? "cursor-not-allowed opacity-50" : "",
              ].join(" ")}
            >
              {d}
            </button>
          );
        })}
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={disabled}
          className={mmActionButtonClass({ variant: "secondary", disabled })}
          onClick={() => preset("all")}
        >
          Every day
        </button>
        <button
          type="button"
          disabled={disabled}
          className={mmActionButtonClass({ variant: "secondary", disabled })}
          onClick={() => preset(["Mon", "Tue", "Wed", "Thu", "Fri"])}
        >
          Weekdays
        </button>
        <button
          type="button"
          disabled={disabled}
          className={mmActionButtonClass({ variant: "secondary", disabled })}
          onClick={() => preset(["Sat", "Sun"])}
        >
          Weekends
        </button>
        <button
          type="button"
          disabled={disabled}
          className={mmActionButtonClass({ variant: "secondary", disabled })}
          onClick={() => preset("clear")}
        >
          Clear
        </button>
      </div>
      <p className="text-xs text-[var(--mm-text3)]">
        {MM_SCHEDULE_DAYS_HELPER}
      </p>
    </div>
  );
}

export function MmScheduleTimeFields({
  idPrefix,
  start,
  end,
  disabled,
  onStart,
  onEnd,
}: {
  idPrefix: string;
  start: string;
  end: string;
  disabled: boolean;
  onStart: (hhmm: string) => void;
  onEnd: (hhmm: string) => void;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <label className="block text-sm text-[var(--mm-text2)]">
        <span className="mb-1 block text-xs text-[var(--mm-text3)]">
          Start time (24-hour)
        </span>
        <input
          id={`${idPrefix}-time-start`}
          type="time"
          step={60}
          className="mm-input w-full max-w-full text-sm tabular-nums tracking-normal text-[var(--mm-text)]"
          value={normalizeScheduleTimeForInput(start)}
          onChange={(e) => onStart(e.target.value)}
          disabled={disabled}
        />
      </label>
      <label className="block text-sm text-[var(--mm-text2)]">
        <span className="mb-1 block text-xs text-[var(--mm-text3)]">
          End time (24-hour)
        </span>
        <input
          id={`${idPrefix}-time-end`}
          type="time"
          step={60}
          className="mm-input w-full max-w-full text-sm tabular-nums tracking-normal text-[var(--mm-text)]"
          value={normalizeScheduleTimeForInput(end)}
          onChange={(e) => onEnd(e.target.value)}
          disabled={disabled}
        />
      </label>
    </div>
  );
}
