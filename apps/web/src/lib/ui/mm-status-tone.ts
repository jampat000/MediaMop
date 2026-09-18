/**
 * The one colour language for status in Weir: a tone, drawn from the `--mm-status-*`
 * tokens, so it reads the same in dark and light. Raw palette colours (`emerald-300`,
 * `red-400`…) are tuned for one theme and all but vanish on the other; nothing that
 * says good, bad or waiting should use them.
 *
 * Processing > Files' status pill is the shape every status pill now shares.
 */
export type MmStatusTone =
  "healthy" | "info" | "warning" | "failed" | "neutral";

const TONE_CLASS: Record<MmStatusTone, string> = {
  healthy:
    "text-[var(--mm-status-healthy-text)] bg-[var(--mm-status-healthy-bg)]",
  info: "text-[var(--mm-status-info-text)] bg-[var(--mm-status-info-bg)]",
  warning:
    "text-[var(--mm-status-warning-text)] bg-[var(--mm-status-warning-bg)]",
  failed: "text-[var(--mm-status-failed-text)] bg-[var(--mm-status-failed-bg)]",
  neutral: "text-[var(--mm-text3)] bg-[var(--mm-well-bg)]",
};

const PILL_BASE =
  "inline-flex items-center whitespace-nowrap rounded-full border border-current px-[0.55rem] py-[0.2rem] text-[0.66rem] font-bold leading-[1.2] tracking-[0.04em]";

/** A small status pill: a word in its tone, on its tone's wash, with a hairline edge. */
export function mmStatusPillClass(tone: MmStatusTone): string {
  return `${PILL_BASE} ${TONE_CLASS[tone]}`;
}
