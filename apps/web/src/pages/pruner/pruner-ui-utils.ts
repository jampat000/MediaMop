import type { PrunerPreviewRunSummary } from "../../lib/pruner/api";

/** Format an API ISO timestamp for operator-facing copy (local timezone). */
export function formatPrunerDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.valueOf())) return "—";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(d);
}

/** Plain-language hint for a single preview run row (trust / empty-state clarity). */
export function previewRunRowCaption(row: PrunerPreviewRunSummary): string {
  if (row.outcome === "unsupported") {
    return row.unsupported_detail?.trim()
      ? `Unsupported for this server: ${row.unsupported_detail.trim()}`
      : "Unsupported for this server on this rule.";
  }
  if (row.outcome === "failed") {
    return row.error_message?.trim()
      ? `Preview job failed: ${row.error_message.trim()}`
      : "Preview job failed; see error above if shown.";
  }
  if (row.outcome === "success" && row.candidate_count === 0) {
    return "Preview finished successfully with zero rows. Often means nothing matched the rule, or preview-only filters removed every candidate — not necessarily a “clean” library.";
  }
  if (row.outcome === "success" && row.candidate_count > 0) {
    return row.truncated
      ? `Matched at least ${row.candidate_count} candidate(s); run was truncated at the configured preview cap.`
      : `${row.candidate_count} candidate(s) in the saved snapshot for this run.`;
  }
  return "";
}

export type PrunerScopeMedia = "tv" | "movies";

/** Rule families that have no honest preview on Plex for the given scope (operator-facing). */
export function plexUnsupportedRuleFamilies(scope: PrunerScopeMedia): string[] {
  if (scope === "tv") {
    return ["Stale never-played library items", "Watched TV (episodes)"];
  }
  return [];
}
