import { fetchActivityRecent } from "../../lib/api/activity-api";
import {
  RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
  RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED,
  RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED,
  RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED,
  RULE_FAMILY_WATCHED_MOVIES_REPORTED,
  RULE_FAMILY_WATCHED_TV_REPORTED,
  fetchPrunerJobsInspection,
  fetchPrunerPreviewRuns,
} from "../../lib/pruner/api";
import type { PrunerServerInstance } from "../../lib/pruner/api";

export const PRUNER_SCAN_POLL_MS = 3000;
export const PRUNER_SCAN_TIMEOUT_MS = 180_000;

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

export function ruleFamilyOperatorLabel(ruleFamilyId: string): string {
  switch (ruleFamilyId) {
    case RULE_FAMILY_WATCHED_TV_REPORTED:
      return "Watched TV removal";
    case RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED:
      return "Never-played stale";
    case RULE_FAMILY_WATCHED_MOVIES_REPORTED:
      return "Watched movies removal";
    case RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED:
      return "Low-rating watched movies";
    case RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED:
      return "Unwatched stale movies";
    case RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED:
      return "Missing primary artwork";
    default:
      return ruleFamilyId;
  }
}

export function parseCommaTokens(raw: string): string[] {
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export function parsePeopleLines(raw: string): string[] {
  return raw
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export type CandidateDisplayRow = {
  key: string;
  title: string;
  ruleLabel: string;
};

export function displayRowsForCandidates(
  candidates: unknown[],
  ruleLabel: string,
): CandidateDisplayRow[] {
  const out: CandidateDisplayRow[] = [];
  let i = 0;
  for (const c of candidates) {
    if (!c || typeof c !== "object") continue;
    const o = c as Record<string, unknown>;
    const title =
      String(o.title ?? "").trim() ||
      String(o.episode_title ?? "").trim() ||
      String(o.series_name ?? "").trim() ||
      String(o.item_id ?? "").trim() ||
      "Untitled";
    out.push({
      key: `${String(o.item_id ?? i)}-${i}`,
      title,
      ruleLabel,
    });
    i += 1;
  }
  return out;
}

export function parseCandidatesJsonArray(raw: string): unknown[] {
  try {
    const v = JSON.parse(raw) as unknown;
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}

export type PreviewSnapshot = {
  previewRunId: string;
  ruleFamilyId: string;
  ruleLabel: string;
  rows: CandidateDisplayRow[];
  truncated: boolean;
  unsupportedDetail: string | null;
  errorMessage: string | null;
  outcome: string;
};

export async function waitForPrunerJobTerminal(
  jobId: number,
  opts: { pollMs?: number; timeoutMs?: number; signal?: AbortSignal } = {},
): Promise<"completed" | "failed"> {
  const pollMs = opts.pollMs ?? PRUNER_SCAN_POLL_MS;
  const timeoutMs = opts.timeoutMs ?? PRUNER_SCAN_TIMEOUT_MS;
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (opts.signal?.aborted) {
      throw new Error("Aborted");
    }
    const data = await fetchPrunerJobsInspection(120);
    const job = data.jobs.find((j) => j.id === jobId);
    const st = job?.status ?? "";
    if (st === "completed") return "completed";
    if (st === "failed" || st === "handler_ok_finalize_failed") return "failed";
    await sleep(pollMs);
  }
  throw new Error("timeout");
}

export async function resolvePreviewRunIdForJob(
  instanceId: number,
  mediaScope: "tv" | "movies",
  jobId: number,
  opts: { pollMs?: number; timeoutMs?: number; signal?: AbortSignal } = {},
): Promise<string | null> {
  const pollMs = opts.pollMs ?? PRUNER_SCAN_POLL_MS;
  const timeoutMs = opts.timeoutMs ?? PRUNER_SCAN_TIMEOUT_MS;
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (opts.signal?.aborted) throw new Error("Aborted");
    const runs = await fetchPrunerPreviewRuns(instanceId, { media_scope: mediaScope, limit: 40 });
    const hit = runs.find((r) => r.pruner_job_id === jobId);
    if (hit?.preview_run_id) return hit.preview_run_id;
    await sleep(pollMs);
  }
  return null;
}

export async function waitForApplyActivity(
  previewRunId: string,
  opts: { pollMs?: number; timeoutMs?: number; signal?: AbortSignal } = {},
): Promise<{ removed: number; skipped: number; failed: number } | null> {
  const pollMs = opts.pollMs ?? PRUNER_SCAN_POLL_MS;
  const timeoutMs = opts.timeoutMs ?? PRUNER_SCAN_TIMEOUT_MS;
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (opts.signal?.aborted) throw new Error("Aborted");
    const recent = await fetchActivityRecent();
    for (const ev of recent.items) {
      if (!ev.detail) continue;
      try {
        const o = JSON.parse(ev.detail) as Record<string, unknown>;
        if (o.phase !== "apply") continue;
        if (String(o.preview_run_id ?? "") !== previewRunId) continue;
        const removed = Number(o.removed);
        const skipped = Number(o.skipped);
        const failed = Number(o.failed);
        if (Number.isFinite(removed) && Number.isFinite(skipped) && Number.isFinite(failed)) {
          return { removed, skipped, failed };
        }
      } catch {
        /* ignore */
      }
    }
    await sleep(pollMs);
  }
  return null;
}

export function tvRuleFamiliesToScan(
  provider: string,
  tv: PrunerServerInstance["scopes"][number],
): string[] {
  const out: string[] = [];
  const p = provider.toLowerCase();
  if (tv.missing_primary_media_reported_enabled) {
    out.push(RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED);
  }
  if (p === "jellyfin" || p === "emby") {
    if (tv.never_played_stale_reported_enabled && tv.never_played_min_age_days >= 7) {
      out.push(RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED);
    }
    if (tv.watched_tv_reported_enabled) {
      out.push(RULE_FAMILY_WATCHED_TV_REPORTED);
    }
  }
  return out;
}

export function moviesRuleFamiliesToScan(
  movies: PrunerServerInstance["scopes"][number],
): string[] {
  const out: string[] = [];
  if (movies.missing_primary_media_reported_enabled) {
    out.push(RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED);
  }
  if (movies.watched_movies_reported_enabled) {
    out.push(RULE_FAMILY_WATCHED_MOVIES_REPORTED);
  }
  if (movies.watched_movie_low_rating_reported_enabled) {
    out.push(RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED);
  }
  if (movies.unwatched_movie_stale_reported_enabled && movies.unwatched_movie_stale_min_age_days >= 7) {
    out.push(RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED);
  }
  return out;
}
