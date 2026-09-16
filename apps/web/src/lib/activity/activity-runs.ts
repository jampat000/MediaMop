/**
 * Plain words for why an Activity entry happened, and one-line summaries of a whole run (#469).
 *
 * Nothing here guesses. An entry without a stated trigger shows no trigger, and a run summary
 * only counts outcomes the entries themselves report.
 */

import type { ActivityEventItem } from "../api/types";

export const ACTIVITY_TRIGGER_LABELS: Record<string, string> = {
  manual: "You started this",
  scheduled: "Schedule",
  webhook: "From your media manager",
  folder_change: "New file in watched folder",
  retry: "Automatic retry",
  startup: "App start",
  worker: "Follow-up",
  system: "System",
};

export const ACTIVITY_RESULT_LABELS: Record<string, string> = {
  success: "Finished",
  skipped: "Skipped",
  warning: "Needs a look",
  retrying: "Will retry",
  running: "In progress",
  failed: "Failed",
};

/** The chip text for an entry's trigger, or null when the entry does not say. */
export function activityTriggerLabel(
  trigger: string | null | undefined,
): string | null {
  if (!trigger) return null;
  return ACTIVITY_TRIGGER_LABELS[trigger] ?? null;
}

const RUN_NAME_BY_TRIGGER: Record<string, string> = {
  manual: "Run you started",
  scheduled: "Scheduled run",
  webhook: "Run from your media manager",
  folder_change: "Run for new files in a watched folder",
  retry: "Automatic retry run",
  startup: "Run at app start",
  worker: "Follow-up run",
  system: "System run",
};

type RunOutcome =
  | "processed"
  | "handed back"
  | "rejected"
  | "no changes needed"
  | "skipped"
  | "failed";

const OUTCOME_ORDER: RunOutcome[] = [
  "processed",
  "handed back",
  "rejected",
  "no changes needed",
  "skipped",
  "failed",
];

function parseDetail(
  detail: string | null | undefined,
): Record<string, unknown> {
  if (!detail?.trim().startsWith("{")) return {};
  try {
    const parsed = JSON.parse(detail) as unknown;
    return parsed && typeof parsed === "object"
      ? (parsed as Record<string, unknown>)
      : {};
  } catch {
    return {};
  }
}

/** What one entry says happened to its file, or null when it is not a final outcome. */
function entryOutcome(ev: ActivityEventItem): RunOutcome | null {
  const type = ev.event_type;
  if (
    type === "refiner.file_passed_through" ||
    type === "refiner.file_reject_fell_back"
  )
    return "handed back";
  if (type === "refiner.file_rejected") return "rejected";
  if (ev.result === "failed") return "failed";
  if (type === "refiner.file_remux_pass_completed") {
    const detail = parseDetail(ev.detail);
    if (detail.pass_through_unchanged === true) return "handed back";
    if (detail.outcome === "live_skipped_not_required")
      return "no changes needed";
    return "processed";
  }
  if (ev.result === "skipped") return "skipped";
  return null;
}

type RunSummary = {
  headline: string;
  failed: number;
};

/** "Scheduled run · 12 files: 8 processed, 2 handed back, 2 no changes needed" */
export function summarizeRun(events: ActivityEventItem[]): RunSummary {
  const trigger = events.find((ev) => ev.trigger)?.trigger ?? null;
  const name = (trigger && RUN_NAME_BY_TRIGGER[trigger]) || "Run";
  const files = new Set(
    events
      .map((ev) => ev.relative_path)
      .filter((path): path is string => Boolean(path)),
  );
  // The newest outcome per file wins, so a retried file is not counted twice.
  const outcomeByKey = new Map<string, RunOutcome>();
  for (const ev of events) {
    const outcome = entryOutcome(ev);
    if (!outcome) continue;
    const key = ev.relative_path ?? `event:${ev.id}`;
    if (!outcomeByKey.has(key)) outcomeByKey.set(key, outcome);
  }
  const counts = new Map<RunOutcome, number>();
  for (const outcome of outcomeByKey.values())
    counts.set(outcome, (counts.get(outcome) ?? 0) + 1);
  const parts = OUTCOME_ORDER.filter((o) => counts.get(o)).map(
    (o) => `${counts.get(o)} ${o}`,
  );
  const size =
    files.size > 0
      ? `${files.size} ${files.size === 1 ? "file" : "files"}`
      : `${events.length} ${events.length === 1 ? "entry" : "entries"}`;
  return {
    headline: `${name} · ${size}${parts.length ? `: ${parts.join(", ")}` : ""}`,
    failed: counts.get("failed") ?? 0,
  };
}
