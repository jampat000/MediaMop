import type { PrunerPreviewRunSummary } from "../../lib/pruner/api";
import { formatAppDate } from "../../lib/ui/mm-format-date";

/** Format an API ISO timestamp for operator-facing copy (browser locale until suite TZ is wired here). */
export function formatPrunerDateTime(iso: string | null | undefined): string {
  return formatAppDate(iso);
}

/** Plain-language hint for a single preview run row (trust / empty-state clarity). */
export function previewRunRowCaption(row: PrunerPreviewRunSummary): string {
  if (row.outcome === "unsupported") {
    return row.unsupported_detail?.trim()
      ? `Not available on this server: ${row.unsupported_detail.trim()}`
      : "This cleanup type is not available on this server.";
  }
  if (row.outcome === "failed") {
    return row.error_message?.trim()
      ? `Scan failed: ${row.error_message.trim()}`
      : "Scan failed; see the message above if one is shown.";
  }
  if (row.outcome === "success" && row.candidate_count === 0) {
    return "Scan finished and nothing matched your rules or filters — your library may still have other items outside this check.";
  }
  if (row.outcome === "success" && row.candidate_count > 0) {
    return row.truncated
      ? `Found at least ${row.candidate_count} item(s); the list stops at your per-run limit so there may be more on the server.`
      : `Found ${row.candidate_count} item(s) ready to review from this scan.`;
  }
  return "";
}

/** Maps internal job kind strings to short operator-facing labels (never shows raw API identifiers). */
export function prunerJobKindOperatorLabel(
  jobKind: string | null | undefined,
): string {
  if (!jobKind?.trim()) return "—";
  const k = jobKind.toLowerCase();
  if (k.includes("apply")) return "Delete run";
  if (k.includes("preview")) return "Library scan";
  if (k.includes("connection")) return "Connection test";
  return "Background task";
}

export type PrunerScopeMedia = "tv" | "movies";

/** Rule families that have no honest preview on Plex for the given scope (operator-facing). */
export function plexUnsupportedRuleFamilies(scope: PrunerScopeMedia): string[] {
  if (scope === "tv") {
    return [
      "TV shows never started, older than your age setting",
      "Watched TV episodes",
    ];
  }
  return [];
}
