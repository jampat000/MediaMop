/** Run-interval draft helpers for Pruner scheduled preview (UI minutes, API seconds). */

export const PRUNER_RUN_INTERVAL_MIN_MINUTES = 1;
export const PRUNER_RUN_INTERVAL_MAX_MINUTES = 7 * 24 * 60;

export function committedPrunerRunIntervalMinutes(seconds: number): string {
  return String(Math.max(PRUNER_RUN_INTERVAL_MIN_MINUTES, Math.round(seconds / 60)));
}

export function finalizePrunerRunIntervalMinutesDraft(draft: string, committedSeconds: number): number {
  const raw = draft.trim();
  if (raw === "") {
    return Math.max(60, committedSeconds);
  }
  const minutes = Number(raw);
  if (!Number.isFinite(minutes)) {
    return Math.max(60, committedSeconds);
  }
  const clamped = Math.min(
    PRUNER_RUN_INTERVAL_MAX_MINUTES,
    Math.max(PRUNER_RUN_INTERVAL_MIN_MINUTES, Math.round(minutes)),
  );
  return clamped * 60;
}
