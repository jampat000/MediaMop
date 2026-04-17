import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { fetchCsrfToken } from "../../lib/api/auth-api";
import { useMeQuery } from "../../lib/auth/queries";
import {
  fetchPrunerApplyEligibility,
  fetchPrunerInstance,
  fetchPrunerPreviewRun,
  patchPrunerScope,
  postPrunerApplyFromPreview,
  postPrunerPreview,
} from "../../lib/pruner/api";
import type { PrunerServerInstance } from "../../lib/pruner/api";
import { MmOnOffSwitch } from "../../components/ui/mm-on-off-switch";
import { fetcherMenuButtonClass } from "../fetcher/fetcher-menu-button";
import {
  PRUNER_SCAN_POLL_MS,
  PRUNER_SCAN_TIMEOUT_MS,
  displayRowsForCandidates,
  moviesRuleFamiliesToScan,
  parseCandidatesJsonArray,
  parseCommaTokens,
  parsePeopleLines,
  resolvePreviewRunIdForJob,
  ruleFamilyOperatorLabel,
  tvRuleFamiliesToScan,
  waitForApplyActivity,
  waitForPrunerJobTerminal,
  type CandidateDisplayRow,
  type PreviewSnapshot,
} from "./pruner-operator-scan-utils";

type ProviderKey = "emby" | "jellyfin" | "plex";

function scopeRow(inst: PrunerServerInstance | undefined, media_scope: "tv" | "movies") {
  return inst?.scopes.find((s) => s.media_scope === media_scope);
}

function parseYear(raw: string): number | null | "bad" {
  const t = raw.trim();
  if (!t) return null;
  const n = Number(t);
  if (!Number.isInteger(n) || n < 1900 || n > 2100) return "bad";
  return n;
}

type DryRunControlsProps = {
  instanceId: number;
  mediaScope: "tv" | "movies";
  testIdPrefix: string;
  /** When true, dry run auto-saves this tab's scope patches before scanning. */
  ensureSaved: () => Promise<void>;
};

function PrunerDryRunControls(props: DryRunControlsProps) {
  const { instanceId, mediaScope, testIdPrefix, ensureSaved } = props;
  const qc = useQueryClient();
  const [phase, setPhase] = useState<"idle" | "scanning" | "results" | "deleting">("idle");
  const [err, setErr] = useState<string | null>(null);
  const [snapshots, setSnapshots] = useState<PreviewSnapshot[]>([]);
  const [deleteEligible, setDeleteEligible] = useState<Record<string, boolean>>({});
  const [deleteReasons, setDeleteReasons] = useState<Record<string, string[]>>({});
  const [applySummary, setApplySummary] = useState<string | null>(null);

  const allRows = useMemo(() => {
    const rows: CandidateDisplayRow[] = [];
    for (const s of snapshots) {
      rows.push(...s.rows);
    }
    return rows;
  }, [snapshots]);

  const totalCount = allRows.length;
  const anyEligible = useMemo(
    () => snapshots.some((s) => s.outcome === "success" && s.rows.length > 0 && deleteEligible[s.previewRunId]),
    [snapshots, deleteEligible],
  );

  async function evaluateEligibility(snaps: PreviewSnapshot[]) {
    const elig: Record<string, boolean> = {};
    const reasons: Record<string, string[]> = {};
    for (const s of snaps) {
      if (s.outcome !== "success" || s.rows.length === 0) continue;
      try {
        const r = await fetchPrunerApplyEligibility(instanceId, mediaScope, s.previewRunId);
        elig[s.previewRunId] = r.eligible;
        reasons[s.previewRunId] = r.reasons;
      } catch {
        elig[s.previewRunId] = false;
        reasons[s.previewRunId] = ["Could not verify delete eligibility."];
      }
    }
    setDeleteEligible(elig);
    setDeleteReasons(reasons);
  }

  async function runScan() {
    setErr(null);
    setApplySummary(null);
    setSnapshots([]);
    setDeleteEligible({});
    setDeleteReasons({});
    setPhase("scanning");
    try {
      await ensureSaved();
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      const fresh = await fetchPrunerInstance(instanceId);
      const tv = scopeRow(fresh, "tv");
      const movies = scopeRow(fresh, "movies");
      if (!tv || !movies) {
        throw new Error("Scope settings missing.");
      }
      const families =
        mediaScope === "tv"
          ? tvRuleFamiliesToScan(fresh.provider, tv)
          : moviesRuleFamiliesToScan(movies);
      if (families.length === 0) {
        setPhase("results");
        setSnapshots([]);
        return;
      }
      const collected: PreviewSnapshot[] = [];
      for (const ruleFamilyId of families) {
        const { pruner_job_id } = await postPrunerPreview(instanceId, mediaScope, { rule_family_id: ruleFamilyId });
        let terminal: "completed" | "failed";
        try {
          terminal = await waitForPrunerJobTerminal(pruner_job_id, {
            pollMs: PRUNER_SCAN_POLL_MS,
            timeoutMs: PRUNER_SCAN_TIMEOUT_MS,
          });
        } catch (e) {
          setErr("Scan is taking longer than expected. Check Activity for results.");
          setPhase("idle");
          return;
        }
        if (terminal === "failed") {
          setErr("Library scan failed. Check Activity for details.");
          setPhase("idle");
          return;
        }
        const previewRunId = await resolvePreviewRunIdForJob(instanceId, mediaScope, pruner_job_id, {
          pollMs: PRUNER_SCAN_POLL_MS,
          timeoutMs: PRUNER_SCAN_TIMEOUT_MS,
        });
        if (!previewRunId) {
          setErr("Scan is taking longer than expected. Check Activity for results.");
          setPhase("idle");
          return;
        }
        const run = await fetchPrunerPreviewRun(instanceId, previewRunId);
        const label = ruleFamilyOperatorLabel(run.rule_family_id);
        const parsed = parseCandidatesJsonArray(run.candidates_json);
        const rows = displayRowsForCandidates(parsed, label);
        collected.push({
          previewRunId: run.preview_run_id,
          ruleFamilyId: run.rule_family_id,
          ruleLabel: label,
          rows,
          truncated: run.truncated,
          unsupportedDetail: run.unsupported_detail,
          errorMessage: run.error_message,
          outcome: run.outcome,
        });
      }
      setSnapshots(collected);
      setPhase("results");
      await evaluateEligibility(collected);
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
    } catch (e) {
      setErr((e as Error).message);
      setPhase("idle");
    }
  }

  async function runDelete() {
    if (!anyEligible) return;
    if (!window.confirm("Delete these library items? This cannot be undone.")) return;
    setErr(null);
    setApplySummary(null);
    setPhase("deleting");
    try {
      let removed = 0;
      let skipped = 0;
      let failed = 0;
      for (const s of snapshots) {
        if (s.outcome !== "success" || s.rows.length === 0) continue;
        if (!deleteEligible[s.previewRunId]) continue;
        const { pruner_job_id } = await postPrunerApplyFromPreview(instanceId, mediaScope, s.previewRunId);
        try {
          await waitForPrunerJobTerminal(pruner_job_id, {
            pollMs: PRUNER_SCAN_POLL_MS,
            timeoutMs: PRUNER_SCAN_TIMEOUT_MS,
          });
        } catch {
          setApplySummary(
            "Delete is taking longer than expected. Check Activity — your server may still be processing items.",
          );
          setPhase("results");
          return;
        }
        const parsed = await waitForApplyActivity(s.previewRunId, {
          pollMs: PRUNER_SCAN_POLL_MS,
          timeoutMs: PRUNER_SCAN_TIMEOUT_MS,
        });
        if (parsed) {
          removed += parsed.removed;
          skipped += parsed.skipped;
          failed += parsed.failed;
        }
      }
      setApplySummary(`Deleted ${removed} items. Skipped ${skipped}. Failed ${failed}.`);
      setPhase("results");
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      await qc.invalidateQueries({ queryKey: ["activity"] });
    } catch (e) {
      setErr((e as Error).message);
      setPhase("results");
    }
  }

  const label = mediaScope === "tv" ? "TV" : "Movies";

  return (
    <div className="mt-8 border-t border-[var(--mm-border)] pt-6" data-testid={`${testIdPrefix}-dry-run-${mediaScope}`}>
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className={fetcherMenuButtonClass({
            variant: "secondary",
            disabled: phase === "scanning" || phase === "deleting",
          })}
          disabled={phase === "scanning" || phase === "deleting"}
          data-testid={`${testIdPrefix}-dry-run-${mediaScope}-btn`}
          onClick={() => void runScan()}
        >
          {phase === "scanning" ? "Scanning your library…" : `Dry run ${label}`}
        </button>
      </div>
      {err ? (
        <p className="mt-3 text-sm text-red-500" role="alert">
          {err}
        </p>
      ) : null}
      {phase === "results" || phase === "deleting" ? (
        <div className="mt-4 space-y-3">
          {phase === "deleting" ? (
            <p className="text-sm font-medium text-[var(--mm-text1)]">Deleting…</p>
          ) : null}
          {snapshots.length === 0 && phase === "results" && !err ? (
            <p className="text-sm text-[var(--mm-text2)]">No enabled rules to scan for this library tab.</p>
          ) : null}
          {snapshots.map((s) => (
            <div key={s.previewRunId} className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-surface2)]/30 p-3">
              <p className="text-sm font-medium text-[var(--mm-text1)]">
                {s.ruleLabel}
                {s.outcome === "unsupported" ? (
                  <span className="ml-2 text-xs font-normal text-[var(--mm-text3)]"> — not available for this scan</span>
                ) : null}
              </p>
              {s.outcome === "unsupported" && s.unsupportedDetail ? (
                <p className="mt-1 text-xs text-[var(--mm-text3)]">{s.unsupportedDetail}</p>
              ) : null}
              {s.outcome === "failed" && s.errorMessage ? (
                <p className="mt-1 text-xs text-red-400">{s.errorMessage}</p>
              ) : null}
              {s.outcome === "success" ? (
                <p className="mt-1 text-xs text-[var(--mm-text2)]">
                  {s.rows.length} match{s.rows.length === 1 ? "" : "es"}
                  {s.truncated ? " (list capped — more items matched on the server)" : ""}
                </p>
              ) : null}
            </div>
          ))}
          {totalCount > 0 ? (
            <p className="text-sm text-[var(--mm-text1)]">
              <span className="font-semibold">{totalCount}</span> item{totalCount === 1 ? "" : "s"} matched across
              enabled rules.
            </p>
          ) : null}
          {totalCount > 0 ? (
            <ul className="max-h-64 divide-y divide-[var(--mm-border)] overflow-y-auto rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] text-sm">
              {allRows.map((r) => (
                <li key={r.key} className="flex flex-col gap-0.5 px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
                  <span className="text-[var(--mm-text1)]">{r.title}</span>
                  <span className="text-xs text-[var(--mm-text3)]">{r.ruleLabel}</span>
                </li>
              ))}
            </ul>
          ) : null}
          {anyEligible ? (
            <button
              type="button"
              className={fetcherMenuButtonClass({ variant: "primary", disabled: phase === "deleting" })}
              disabled={phase === "deleting"}
              data-testid={`${testIdPrefix}-delete-these-${mediaScope}`}
              onClick={() => void runDelete()}
            >
              Delete these
            </button>
          ) : null}
          {snapshots.some((s) => s.outcome === "success" && s.rows.length > 0 && deleteEligible[s.previewRunId] === false) ? (
            <div className="text-xs text-[var(--mm-text3)]">
              {snapshots.map((s) => {
                if (s.outcome !== "success" || s.rows.length === 0 || deleteEligible[s.previewRunId] !== false) return null;
                const rs = deleteReasons[s.previewRunId] ?? [];
                return (
                  <p key={s.previewRunId} className="mt-1">
                    <span className="font-medium text-[var(--mm-text2)]">{s.ruleLabel}:</span> {rs.join(" ")}
                  </p>
                );
              })}
            </div>
          ) : null}
          {applySummary ? <p className="text-sm text-[var(--mm-text1)]">{applySummary}</p> : null}
          <p className="text-xs text-[var(--mm-text3)]">
            Full audit trail:{" "}
            <Link to="/app/activity" className="font-medium text-[var(--mm-accent)] underline-offset-2 hover:underline">
              Activity
            </Link>
          </p>
        </div>
      ) : null}
    </div>
  );
}

type RulesCardProps = {
  provider: ProviderKey;
  instanceId: number;
  instance: PrunerServerInstance;
  disabled: boolean;
};

export function PrunerProviderRulesCard({ provider, instanceId, instance, disabled }: RulesCardProps) {
  const qc = useQueryClient();
  const me = useMeQuery();
  const canOperate = me.data?.role === "admin" || me.data?.role === "operator";
  const isPlex = provider === "plex";
  const tv = scopeRow(instance, "tv");
  const movies = scopeRow(instance, "movies");

  const [missingPrimaryTv, setMissingPrimaryTv] = useState(true);
  const [watchedTv, setWatchedTv] = useState(false);
  const [neverTvDays, setNeverTvDays] = useState("0");
  const [genreTv, setGenreTv] = useState("");
  const [yearMinTv, setYearMinTv] = useState("");
  const [yearMaxTv, setYearMaxTv] = useState("");
  const [studioTv, setStudioTv] = useState("");

  const [missingPrimaryMovies, setMissingPrimaryMovies] = useState(true);
  const [watchedMovies, setWatchedMovies] = useState(false);
  const [lowRatingMovies, setLowRatingMovies] = useState("0");
  const [unwatchedDays, setUnwatchedDays] = useState("0");
  const [genreMovies, setGenreMovies] = useState("");
  const [yearMinMovies, setYearMinMovies] = useState("");
  const [yearMaxMovies, setYearMaxMovies] = useState("");
  const [studioMovies, setStudioMovies] = useState("");

  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!tv) return;
    setMissingPrimaryTv(tv.missing_primary_media_reported_enabled);
    setWatchedTv(tv.watched_tv_reported_enabled);
    setNeverTvDays(!tv.never_played_stale_reported_enabled ? "0" : String(tv.never_played_min_age_days));
    setGenreTv((tv.preview_include_genres ?? []).join(", "));
    setYearMinTv(tv.preview_year_min != null ? String(tv.preview_year_min) : "");
    setYearMaxTv(tv.preview_year_max != null ? String(tv.preview_year_max) : "");
    setStudioTv((tv.preview_include_studios ?? []).join(", "));
  }, [tv]);

  useEffect(() => {
    if (!movies) return;
    setMissingPrimaryMovies(movies.missing_primary_media_reported_enabled);
    setWatchedMovies(movies.watched_movies_reported_enabled);
    setLowRatingMovies(
      !movies.watched_movie_low_rating_reported_enabled
        ? "0"
        : String(
            isPlex
              ? movies.watched_movie_low_rating_max_plex_audience_rating
              : movies.watched_movie_low_rating_max_jellyfin_emby_community_rating,
          ),
    );
    setUnwatchedDays(!movies.unwatched_movie_stale_reported_enabled ? "0" : String(movies.unwatched_movie_stale_min_age_days));
    setGenreMovies((movies.preview_include_genres ?? []).join(", "));
    setYearMinMovies(movies.preview_year_min != null ? String(movies.preview_year_min) : "");
    setYearMaxMovies(movies.preview_year_max != null ? String(movies.preview_year_max) : "");
    setStudioMovies((movies.preview_include_studios ?? []).join(", "));
  }, [movies, isPlex]);

  function buildFilterPatch(
    scope: "tv" | "movies",
    genreText: string,
    yMinStr: string,
    yMaxStrStr: string,
    studioText: string,
  ) {
    const yMin = parseYear(yMinStr);
    const yMax = parseYear(yMaxStrStr);
    if (yMin === "bad" || yMax === "bad") {
      throw new Error("Each year must be a whole number between 1900 and 2100, or left empty.");
    }
    if (yMin != null && yMax != null && yMin > yMax) {
      throw new Error("Minimum year must be less than or equal to maximum year.");
    }
    return {
      preview_include_genres: parseCommaTokens(genreText),
      preview_year_min: yMinStr.trim() ? yMin : null,
      preview_year_max: yMaxStrStr.trim() ? yMax : null,
      preview_include_studios: parseCommaTokens(studioText),
      ...(isPlex && scope === "movies" ? { preview_include_collections: movies?.preview_include_collections ?? [] } : {}),
    };
  }

  async function persistTv(): Promise<void> {
    if (!tv) return;
    const csrf_token = await fetchCsrfToken();
    const raw = parseInt(neverTvDays.trim(), 10);
    const neverOn = !isPlex && Number.isFinite(raw) && raw >= 7;
    const neverDays = neverOn ? Math.max(7, Math.min(3650, raw)) : 90;
    const filters = buildFilterPatch("tv", genreTv, yearMinTv, yearMaxTv, studioTv);
    await patchPrunerScope(instanceId, "tv", {
      missing_primary_media_reported_enabled: missingPrimaryTv,
      watched_tv_reported_enabled: watchedTv,
      never_played_stale_reported_enabled: neverOn,
      never_played_min_age_days: neverDays,
      ...filters,
      csrf_token,
    });
    await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
  }

  async function persistMovies(): Promise<void> {
    if (!movies) return;
    const csrf_token = await fetchCsrfToken();
    const lowRaw = Number.parseFloat(lowRatingMovies.trim());
    const lowOn = Number.isFinite(lowRaw) && lowRaw > 0;
    const cap = lowOn ? Math.max(0, Math.min(10, lowRaw)) : 4;
    const uwRaw = parseInt(unwatchedDays.trim(), 10);
    const uwOn = Number.isFinite(uwRaw) && uwRaw >= 7;
    const uwDays = uwOn ? Math.max(7, Math.min(3650, uwRaw)) : 90;
    const filters = buildFilterPatch("movies", genreMovies, yearMinMovies, yearMaxMovies, studioMovies);
    await patchPrunerScope(instanceId, "movies", {
      missing_primary_media_reported_enabled: missingPrimaryMovies,
      watched_movies_reported_enabled: watchedMovies,
      watched_movie_low_rating_reported_enabled: lowOn,
      ...(isPlex
        ? { watched_movie_low_rating_max_plex_audience_rating: cap }
        : { watched_movie_low_rating_max_jellyfin_emby_community_rating: cap }),
      unwatched_movie_stale_reported_enabled: uwOn,
      unwatched_movie_stale_min_age_days: uwDays,
      ...filters,
      csrf_token,
    });
    await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
  }

  async function saveTv() {
    if (!tv) return;
    setErr(null);
    setMsg(null);
    setBusy(true);
    try {
      await persistTv();
      setMsg("Saved TV rules.");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function saveMovies() {
    if (!movies) return;
    setErr(null);
    setMsg(null);
    setBusy(true);
    try {
      await persistMovies();
      setMsg("Saved Movies rules.");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function ensureRulesSavedForDryRun() {
    await persistTv();
    await persistMovies();
  }

  const fieldDisabled = disabled || !canOperate || busy;

  return (
    <div
      className="mm-card mm-dash-card border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5 sm:p-6"
      data-testid={`pruner-provider-configuration-${provider}`}
      data-provider-section="rules"
    >
      <div className="grid gap-8 lg:grid-cols-2 lg:gap-10">
        <fieldset disabled={fieldDisabled || disabled} className="min-w-0 border-0 p-0">
          <div className="min-w-0 space-y-5" data-testid={`pruner-provider-tv-config-${provider}`}>
            <div className="flex items-center gap-2 border-b border-[var(--mm-border)] pb-2">
              <span className="text-sm font-semibold uppercase tracking-wide text-[var(--mm-text1)]">TV</span>
            </div>
            {isPlex ? (
              <div
                className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-surface2)]/25 px-3 py-2 text-xs text-[var(--mm-text3)]"
                data-testid="pruner-provider-plex-tv-unsupported-rules"
              >
                <p>Never-played TV older than N days — not supported for Plex.</p>
                <p className="mt-2">Watched TV removal — not supported for Plex.</p>
              </div>
            ) : (
              <>
                <MmOnOffSwitch
                  id={`pruner-op-tv-watched-${provider}`}
                  label="Watched TV removal — Delete items marked watched for this user"
                  enabled={watchedTv}
                  disabled={fieldDisabled || disabled}
                  onChange={setWatchedTv}
                />
                <label className="block text-sm text-[var(--mm-text1)]">
                  <span className="mb-1 block text-xs text-[var(--mm-text3)]">Never-played TV older than N days</span>
                  <input
                    type="number"
                    min={0}
                    max={3650}
                    className="mm-input w-full max-w-xs"
                    value={neverTvDays}
                    onChange={(e) => setNeverTvDays(e.target.value)}
                    disabled={fieldDisabled || disabled}
                  />
                </label>
                <p className="text-xs text-[var(--mm-text3)]">Set 0 to disable.</p>
              </>
            )}
            <MmOnOffSwitch
              id={`pruner-op-tv-missing-${provider}`}
              label="Remove items missing primary artwork — Broken or missing poster / episode image"
              enabled={missingPrimaryTv}
              disabled={fieldDisabled || disabled}
              onChange={setMissingPrimaryTv}
            />
            {isPlex ? (
              <p className="text-xs text-[var(--mm-text3)]" data-testid="pruner-plex-tv-filters-scope-note">
                Genre, year, and studio filters apply to missing-artwork scans on this tab.
              </p>
            ) : null}
            <CommaField
              label="Genre"
              placeholder="e.g. Drama, Science Fiction"
              helper="Leave blank for all genres"
              value={genreTv}
              onChange={setGenreTv}
              disabled={fieldDisabled || disabled}
            />
            <YearRange min={yearMinTv} max={yearMaxTv} onMin={setYearMinTv} onMax={setYearMaxTv} disabled={fieldDisabled || disabled} />
            <CommaField
              label="Studio"
              placeholder="e.g. Warner Bros., BBC"
              helper="Leave blank for all studios"
              value={studioTv}
              onChange={setStudioTv}
              disabled={fieldDisabled || disabled}
            />
            {canOperate ? (
              <button
                type="button"
                className={fetcherMenuButtonClass({ variant: "primary", disabled: busy || disabled })}
                disabled={busy || disabled}
                onClick={() => void saveTv()}
              >
                {busy ? "Saving…" : "Save TV rules"}
              </button>
            ) : null}
          </div>
        </fieldset>

        <fieldset disabled={fieldDisabled || disabled} className="min-w-0 border-0 p-0 lg:border-l lg:border-[var(--mm-border)] lg:pl-8">
          <div className="min-w-0 space-y-5" data-testid={`pruner-provider-movies-config-${provider}`}>
            <div className="flex items-center gap-2 border-b border-[var(--mm-border)] pb-2">
              <span className="text-sm font-semibold uppercase tracking-wide text-[var(--mm-text1)]">Movies</span>
            </div>
            <MmOnOffSwitch
              id={`pruner-op-mov-watched-${provider}`}
              label="Watched movies removal — Delete items marked watched for this user"
              enabled={watchedMovies}
              disabled={fieldDisabled || disabled}
              onChange={setWatchedMovies}
            />
            <label className="block text-sm text-[var(--mm-text1)]">
              {isPlex ? "Plex audienceRating max (0–10)" : "Jellyfin/Emby CommunityRating max (0–10)"}
              <input
                type="number"
                min={0}
                max={10}
                step={0.1}
                className="mm-input mt-1 w-full max-w-xs"
                value={lowRatingMovies}
                onChange={(e) => setLowRatingMovies(e.target.value)}
                disabled={fieldDisabled || disabled}
              />
            </label>
            <p className="text-xs text-[var(--mm-text3)]">Set 0 to disable low-rating removal.</p>
            <label className="block text-sm text-[var(--mm-text2)]">
              <span className="mb-1 block text-xs text-[var(--mm-text3)]">Unwatched movies older than N days</span>
              <input
                type="number"
                min={0}
                max={3650}
                className="mm-input w-full max-w-xs"
                value={unwatchedDays}
                onChange={(e) => setUnwatchedDays(e.target.value)}
                disabled={fieldDisabled || disabled}
              />
            </label>
            <p className="text-xs text-[var(--mm-text3)]">Set 0 to disable.</p>
            <MmOnOffSwitch
              id={`pruner-op-mov-missing-${provider}`}
              label="Remove items missing primary artwork — Broken or missing movie poster"
              enabled={missingPrimaryMovies}
              disabled={fieldDisabled || disabled}
              onChange={setMissingPrimaryMovies}
            />
            {isPlex ? (
              <p className="text-xs text-[var(--mm-text3)]" data-testid="pruner-plex-other-rules-note">
                Plex scans use your server metadata; large libraries may return capped lists.
              </p>
            ) : null}
            <CommaField
              label="Genre"
              placeholder="e.g. Drama, Science Fiction"
              helper="Leave blank for all genres"
              value={genreMovies}
              onChange={setGenreMovies}
              disabled={fieldDisabled || disabled}
            />
            <YearRange
              min={yearMinMovies}
              max={yearMaxMovies}
              onMin={setYearMinMovies}
              onMax={setYearMaxMovies}
              disabled={fieldDisabled || disabled}
            />
            <CommaField
              label="Studio"
              placeholder="e.g. Warner Bros., BBC"
              helper="Leave blank for all studios"
              value={studioMovies}
              onChange={setStudioMovies}
              disabled={fieldDisabled || disabled}
            />
            {canOperate ? (
              <button
                type="button"
                className={fetcherMenuButtonClass({ variant: "primary", disabled: busy || disabled })}
                disabled={busy || disabled}
                onClick={() => void saveMovies()}
              >
                {busy ? "Saving…" : "Save Movies rules"}
              </button>
            ) : null}
          </div>
        </fieldset>
      </div>

      {!disabled ? (
        <>
          <PrunerDryRunControls
            instanceId={instanceId}
            mediaScope="tv"
            testIdPrefix="pruner-rules"
            ensureSaved={ensureRulesSavedForDryRun}
          />
          <PrunerDryRunControls
            instanceId={instanceId}
            mediaScope="movies"
            testIdPrefix="pruner-rules"
            ensureSaved={ensureRulesSavedForDryRun}
          />
        </>
      ) : null}

      {msg ? (
        <p className="mt-4 text-sm text-green-600" role="status">
          {msg}
        </p>
      ) : null}
      {err ? (
        <p className="mt-2 text-sm text-red-500" role="alert">
          {err}
        </p>
      ) : null}
    </div>
  );
}

function CommaField({
  label,
  placeholder,
  helper,
  value,
  onChange,
  disabled,
}: {
  label: string;
  placeholder: string;
  helper: string;
  value: string;
  onChange: (v: string) => void;
  disabled: boolean;
}) {
  return (
    <label className="block text-sm text-[var(--mm-text2)]">
      <span className="mb-1 block text-xs font-medium text-[var(--mm-text3)]">{label}</span>
      <input
        type="text"
        className="mm-input w-full"
        placeholder={placeholder}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      />
      <span className="mt-1 block text-xs text-[var(--mm-text3)]">{helper}</span>
    </label>
  );
}

function YearRange({
  min,
  max,
  onMin,
  onMax,
  disabled,
}: {
  min: string;
  max: string;
  onMin: (v: string) => void;
  onMax: (v: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="space-y-1">
      <span className="text-xs font-medium text-[var(--mm-text3)]">Year range</span>
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm text-[var(--mm-text2)]">
          Min year
          <input type="text" inputMode="numeric" className="mm-input ml-2 w-28" value={min} disabled={disabled} onChange={(e) => onMin(e.target.value)} />
        </label>
        <label className="text-sm text-[var(--mm-text2)]">
          Max year
          <input type="text" inputMode="numeric" className="mm-input ml-2 w-28" value={max} disabled={disabled} onChange={(e) => onMax(e.target.value)} />
        </label>
      </div>
      <p className="text-xs text-[var(--mm-text3)]">Leave blank for open-ended.</p>
    </div>
  );
}

type PeopleCardProps = {
  provider: ProviderKey;
  instanceId: number;
  instance: PrunerServerInstance;
  disabled: boolean;
};

export function PrunerProviderPeopleCard({ provider, instanceId, instance, disabled }: PeopleCardProps) {
  const qc = useQueryClient();
  const me = useMeQuery();
  const canOperate = me.data?.role === "admin" || me.data?.role === "operator";
  const tv = scopeRow(instance, "tv");
  const movies = scopeRow(instance, "movies");
  const [tvPeople, setTvPeople] = useState("");
  const [moviesPeople, setMoviesPeople] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setTvPeople(((tv?.preview_include_people ?? []) as string[]).join("\n"));
  }, [tv?.preview_include_people]);

  useEffect(() => {
    setMoviesPeople(((movies?.preview_include_people ?? []) as string[]).join("\n"));
  }, [movies?.preview_include_people]);

  async function persistTvPeople(): Promise<void> {
    if (!tv) return;
    const csrf_token = await fetchCsrfToken();
    await patchPrunerScope(instanceId, "tv", {
      preview_include_people: parsePeopleLines(tvPeople),
      csrf_token,
    });
    await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
  }

  async function persistMoviesPeople(): Promise<void> {
    if (!movies) return;
    const csrf_token = await fetchCsrfToken();
    await patchPrunerScope(instanceId, "movies", {
      preview_include_people: parsePeopleLines(moviesPeople),
      csrf_token,
    });
    await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
  }

  async function saveTvPeople() {
    if (!tv) return;
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      await persistTvPeople();
      setMsg("Saved TV people.");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function saveMoviesPeople() {
    if (!movies) return;
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      await persistMoviesPeople();
      setMsg("Saved Movies people.");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function ensurePeopleSavedForDryRun() {
    await persistTvPeople();
    await persistMoviesPeople();
  }

  const fieldDisabled = disabled || !canOperate || busy;

  return (
    <div
      className="mm-card mm-dash-card border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5 sm:p-6"
      data-testid={`pruner-provider-people-card-${provider}`}
      data-provider-section="people"
    >
      <div className="grid gap-8 lg:grid-cols-2 lg:gap-10">
        <fieldset disabled={fieldDisabled || disabled} className="min-w-0 border-0 p-0">
          <div className="min-w-0 space-y-3" data-testid={`pruner-provider-tv-people-${provider}`}>
            <div className="flex items-center gap-2 border-b border-[var(--mm-border)] pb-2">
              <span className="text-sm font-semibold uppercase tracking-wide text-[var(--mm-text1)]">TV</span>
            </div>
            <label className="block text-sm text-[var(--mm-text2)]">
              <span className="mb-1 block text-xs text-[var(--mm-text3)]">Names</span>
              <textarea
                className="mm-input min-h-[7rem] w-full font-sans text-sm"
                rows={5}
                placeholder="e.g. Alex Carter, Jordan Lee (comma or one per line)"
                value={tvPeople}
                disabled={fieldDisabled || disabled}
                onChange={(e) => setTvPeople(e.target.value)}
              />
            </label>
            <p className="text-xs text-[var(--mm-text3)]">Leave blank to use no name filter.</p>
            {canOperate ? (
              <button
                type="button"
                className={fetcherMenuButtonClass({ variant: "primary", disabled: busy || disabled })}
                disabled={busy || disabled}
                onClick={() => void saveTvPeople()}
              >
                {busy ? "Saving…" : "Save TV people"}
              </button>
            ) : null}
          </div>
        </fieldset>
        <fieldset disabled={fieldDisabled || disabled} className="min-w-0 border-0 p-0 lg:border-l lg:border-[var(--mm-border)] lg:pl-8">
          <div className="min-w-0 space-y-3" data-testid={`pruner-provider-movies-people-${provider}`}>
            <div className="flex items-center gap-2 border-b border-[var(--mm-border)] pb-2">
              <span className="text-sm font-semibold uppercase tracking-wide text-[var(--mm-text1)]">Movies</span>
            </div>
            <label className="block text-sm text-[var(--mm-text2)]">
              <span className="mb-1 block text-xs text-[var(--mm-text3)]">Names</span>
              <textarea
                className="mm-input min-h-[7rem] w-full font-sans text-sm"
                rows={5}
                placeholder="e.g. Alex Carter, Jordan Lee (comma or one per line)"
                value={moviesPeople}
                disabled={fieldDisabled || disabled}
                onChange={(e) => setMoviesPeople(e.target.value)}
              />
            </label>
            <p className="text-xs text-[var(--mm-text3)]">Leave blank to use no name filter.</p>
            {canOperate ? (
              <button
                type="button"
                className={fetcherMenuButtonClass({ variant: "primary", disabled: busy || disabled })}
                disabled={busy || disabled}
                onClick={() => void saveMoviesPeople()}
              >
                {busy ? "Saving…" : "Save Movies people"}
              </button>
            ) : null}
          </div>
        </fieldset>
      </div>
      {!disabled ? (
        <>
          <PrunerDryRunControls
            instanceId={instanceId}
            mediaScope="tv"
            testIdPrefix="pruner-people"
            ensureSaved={ensurePeopleSavedForDryRun}
          />
          <PrunerDryRunControls
            instanceId={instanceId}
            mediaScope="movies"
            testIdPrefix="pruner-people"
            ensureSaved={ensurePeopleSavedForDryRun}
          />
        </>
      ) : null}
      {msg ? (
        <p className="mt-4 text-sm text-green-600" role="status">
          {msg}
        </p>
      ) : null}
      {err ? (
        <p className="mt-2 text-sm text-red-500" role="alert">
          {err}
        </p>
      ) : null}
    </div>
  );
}
