/**
 * Shared **module top-tab** context strip (Pruner, Refiner, Subber, …).
 * Same visual rhythm as Suite Settings tab blurbs: double horizontal rule and even vertical padding.
 */

export const mmModuleTabBlurbBandClass =
  "border-t border-b border-[var(--mm-border)] py-5";

/** One-line tab context copy (no `mt-*` — the band’s `py-5` sets vertical rhythm). */
export const mmModuleTabBlurbTextClass =
  "max-w-3xl text-sm leading-snug text-[var(--mm-text2)]";
