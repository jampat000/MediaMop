import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState, type ReactNode } from "react";
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
import { PrunerGenreMultiSelect, prunerGenresFromApi } from "./pruner-genre-multi-select";
import { PrunerStudioMultiSelect } from "./pruner-studio-multi-select";
import {
  DEFAULT_PRUNER_PEOPLE_ROLES,
  PrunerPeopleRoleCheckboxes,
  normalizePeopleRolesFromApi,
  peopleRolesForPlexPersist,
  peopleRolesForPlexUiState,
  type PrunerPeopleRoleId,
} from "./pruner-people-roles";
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

type PrunerDryRunControlsProps = {
  instanceId: number;
  mediaScope: "tv" | "movies";
  testIdPrefix: string;
  ensureSaved: () => Promise<void>;
  dryRunEnabled: boolean;
  onDryRunEnabledChange: (enabled: boolean) => void;
  runDisabled: boolean;
  controlsDisabled: boolean;
  /** Rendered after the Run button (e.g. Save + status) and before scan/delete results. */
  afterRunSlot?: ReactNode;
};

async function evaluateEligibilityForSnapshots(
  instanceId: number,
  mediaScope: "tv" | "movies",
  snaps: PreviewSnapshot[],
): Promise<{ elig: Record<string, boolean>; reasons: Record<string, string[]> }> {
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
      reasons[s.previewRunId] = ["Could not confirm whether these items can be deleted safely."];
    }
  }
  return { elig, reasons };
}

/** Dry-run toggle, run button, and scan/delete results for one media column. */
export function PrunerDryRunControls(props: PrunerDryRunControlsProps) {
  const {
    instanceId,
    mediaScope,
    testIdPrefix,
    ensureSaved,
    dryRunEnabled,
    onDryRunEnabledChange,
    runDisabled,
    controlsDisabled,
    afterRunSlot,
  } = props;
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
  const [emptyBecauseNoRules, setEmptyBecauseNoRules] = useState(false);

  async function runCleanupNow() {
    setErr(null);
    setApplySummary(null);
    setSnapshots([]);
    setDeleteEligible({});
    setDeleteReasons({});
    setPhase("scanning");
    setEmptyBecauseNoRules(false);
    try {
      await ensureSaved();
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      const fresh = await fetchPrunerInstance(instanceId);
      const tv = scopeRow(fresh, "tv");
      const movies = scopeRow(fresh, "movies");
      if (!tv || !movies) {
        throw new Error("TV and movie settings for this server are missing. Try reloading the page.");
      }
      const families =
        mediaScope === "tv" ? tvRuleFamiliesToScan(fresh.provider, tv) : moviesRuleFamiliesToScan(movies);
      if (families.length === 0) {
        setSnapshots([]);
        setEmptyBecauseNoRules(true);
        setPhase("results");
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
        } catch {
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

      const { elig, reasons } = await evaluateEligibilityForSnapshots(instanceId, mediaScope, collected);
      setSnapshots(collected);
      setDeleteEligible(elig);
      setDeleteReasons(reasons);

      const rowsCount = collected.reduce((acc, s) => acc + s.rows.length, 0);
      const eligibleAny = collected.some(
        (s) => s.outcome === "success" && s.rows.length > 0 && elig[s.previewRunId] === true,
      );

      if (dryRunEnabled) {
        setPhase("results");
        await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
        return;
      }

      if (rowsCount === 0) {
        setPhase("results");
        await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
        return;
      }

      if (!eligibleAny) {
        setPhase("results");
        await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
        return;
      }

      setPhase("deleting");
      let removed = 0;
      let skipped = 0;
      let failed = 0;
      for (const s of collected) {
        if (s.outcome !== "success" || s.rows.length === 0) continue;
        if (!elig[s.previewRunId]) continue;
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
          await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
          await qc.invalidateQueries({ queryKey: ["activity"] });
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
      setSnapshots([]);
      setDeleteEligible({});
      setDeleteReasons({});
      setApplySummary(`Deleted ${removed} items. Skipped ${skipped}. Failed ${failed}.`);
      setPhase("results");
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      await qc.invalidateQueries({ queryKey: ["activity"] });
    } catch (e) {
      setErr((e as Error).message);
      setPhase("idle");
    }
  }

  const runLabel = mediaScope === "tv" ? "Run TV cleanup now" : "Run Movies cleanup now";
  const runBusy = phase === "scanning" || phase === "deleting";
  const runBtnDisabled = runDisabled || controlsDisabled || runBusy;

  return (
    <div className="min-w-0 space-y-4" data-testid={`${testIdPrefix}-run-${mediaScope}`}>
      <MmOnOffSwitch
        id={`${testIdPrefix}-dry-run-${mediaScope}`}
        label="Dry run"
        enabled={dryRunEnabled}
        disabled={controlsDisabled}
        onChange={onDryRunEnabledChange}
      />
      <p className="text-xs text-[var(--mm-text3)]">
        {dryRunEnabled
          ? "Dry run is ON — Run will show you what would be deleted. Nothing is deleted until you turn dry run off."
          : "Dry run is OFF — Run will immediately and permanently delete everything that matches. We strongly recommend doing a dry run first."}
      </p>
      <div>
        <button
          type="button"
          className={fetcherMenuButtonClass({
            variant: "primary",
            disabled: runBtnDisabled,
          })}
          disabled={runBtnDisabled}
          data-testid={`${testIdPrefix}-run-${mediaScope}-btn`}
          onClick={() => void runCleanupNow()}
        >
          {phase === "scanning" ? "Scanning…" : runLabel}
        </button>
      </div>
      {afterRunSlot ? <div className="space-y-3">{afterRunSlot}</div> : null}
      {err ? (
        <p className="text-sm text-red-500" role="alert">
          {err}
        </p>
      ) : null}
      {phase === "results" || phase === "deleting" ? (
        <div className="mt-4 space-y-3">
          {phase === "deleting" ? (
            <p className="text-sm font-medium text-[var(--mm-text1)]">Deleting…</p>
          ) : null}
          {snapshots.length === 0 && phase === "results" && !err && emptyBecauseNoRules ? (
            <p className="text-sm text-[var(--mm-text2)]">
              No cleanup rules are turned on for this column, so there is nothing to scan.
            </p>
          ) : null}
          {!dryRunEnabled && phase === "results" && snapshots.length > 0 && totalCount === 0 ? (
            <p className="text-sm text-[var(--mm-text2)]">No items matched your criteria.</p>
          ) : null}
          {(dryRunEnabled || !applySummary) &&
            snapshots.map((s) => (
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
                    {s.rows.length} item{s.rows.length === 1 ? "" : "s"} matched
                    {s.truncated ? " (list stopped at your scan limit — more may exist on the server)" : ""}
                  </p>
                ) : null}
              </div>
            ))}
          {dryRunEnabled && phase === "results" && snapshots.length > 0 ? (
            totalCount > 0 ? (
              <>
                <p className="text-sm text-[var(--mm-text1)]">
                  <span className="font-semibold">{totalCount}</span> item{totalCount === 1 ? "" : "s"} matched your
                  criteria.
                </p>
                <ul className="max-h-64 divide-y divide-[var(--mm-border)] overflow-y-auto rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] text-sm">
                  {allRows.map((r) => (
                    <li key={r.key} className="flex flex-col gap-0.5 px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
                      <span className="text-[var(--mm-text1)]">{r.title}</span>
                      <span className="text-xs text-[var(--mm-text3)]">{r.ruleLabel}</span>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <p className="text-sm text-[var(--mm-text2)]">No items matched your criteria.</p>
            )
          ) : null}
          {!dryRunEnabled && snapshots.some((s) => s.outcome === "success" && s.rows.length > 0 && deleteEligible[s.previewRunId] === false) ? (
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
          {applySummary ? (
            <p className="text-sm text-[var(--mm-text1)]">
              {applySummary.includes("taking longer") ? (
                applySummary
              ) : (
                <>
                  {applySummary}{" "}
                  <Link to="/app/activity" className="font-semibold text-[var(--mm-accent)] underline-offset-2 hover:underline">
                    Activity log
                  </Link>{" "}
                  has full detail.
                </>
              )}
            </p>
          ) : null}
          {dryRunEnabled && phase === "results" && totalCount > 0 ? (
            <p className="text-xs text-[var(--mm-text3)]">
              Full detail:{" "}
              <Link to="/app/activity" className="font-medium text-[var(--mm-accent)] underline-offset-2 hover:underline">
                Activity log
              </Link>
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

type RulesCardProps = {
  provider: ProviderKey;
  instanceId: number;
  instance: PrunerServerInstance;
};

export type PrunerProviderRulesCardHandle = {
  ensureTvSaved: () => Promise<void>;
  ensureMoviesSaved: () => Promise<void>;
};

export const PrunerProviderRulesCard = forwardRef<PrunerProviderRulesCardHandle, RulesCardProps>(
  function PrunerProviderRulesCard({ provider, instanceId, instance }, ref) {
  const qc = useQueryClient();
  const me = useMeQuery();
  const canOperate = me.data?.role === "admin" || me.data?.role === "operator";
  const isPlex = provider === "plex";
  const tv = scopeRow(instance, "tv");
  const movies = scopeRow(instance, "movies");

  const [missingPrimaryTv, setMissingPrimaryTv] = useState(true);
  const [watchedTv, setWatchedTv] = useState(false);
  const [neverTvDays, setNeverTvDays] = useState("0");
  const [genreTv, setGenreTv] = useState<string[]>([]);
  const [yearMinTv, setYearMinTv] = useState("");
  const [yearMaxTv, setYearMaxTv] = useState("");
  const [studioTv, setStudioTv] = useState<string[]>([]);
  const [tvPeople, setTvPeople] = useState("");
  const [tvRoles, setTvRoles] = useState<PrunerPeopleRoleId[]>([...DEFAULT_PRUNER_PEOPLE_ROLES]);
  const [tvRolesCoerceMsg, setTvRolesCoerceMsg] = useState<string | null>(null);

  const [missingPrimaryMovies, setMissingPrimaryMovies] = useState(true);
  const [watchedMovies, setWatchedMovies] = useState(false);
  const [lowRatingMovies, setLowRatingMovies] = useState("0");
  const [unwatchedDays, setUnwatchedDays] = useState("0");
  const [genreMovies, setGenreMovies] = useState<string[]>([]);
  const [yearMinMovies, setYearMinMovies] = useState("");
  const [yearMaxMovies, setYearMaxMovies] = useState("");
  const [studioMovies, setStudioMovies] = useState<string[]>([]);
  const [moviesPeople, setMoviesPeople] = useState("");
  const [moviesRoles, setMoviesRoles] = useState<PrunerPeopleRoleId[]>([...DEFAULT_PRUNER_PEOPLE_ROLES]);
  const [moviesRolesCoerceMsg, setMoviesRolesCoerceMsg] = useState<string | null>(null);
  const [moviesCollections, setMoviesCollections] = useState("");

  const [busyTv, setBusyTv] = useState(false);
  const [busyMovies, setBusyMovies] = useState(false);
  const [msgTv, setMsgTv] = useState<string | null>(null);
  const [msgMovies, setMsgMovies] = useState<string | null>(null);
  const [errTv, setErrTv] = useState<string | null>(null);
  const [errMovies, setErrMovies] = useState<string | null>(null);

  useEffect(() => {
    if (!tv) return;
    setMissingPrimaryTv(tv.missing_primary_media_reported_enabled);
    setWatchedTv(tv.watched_tv_reported_enabled);
    setNeverTvDays(!tv.never_played_stale_reported_enabled ? "0" : String(tv.never_played_min_age_days));
    setGenreTv(prunerGenresFromApi(tv.preview_include_genres));
    setYearMinTv(tv.preview_year_min != null ? String(tv.preview_year_min) : "");
    setYearMaxTv(tv.preview_year_max != null ? String(tv.preview_year_max) : "");
    setStudioTv([...(tv.preview_include_studios ?? [])]);
    setTvPeople(((tv.preview_include_people ?? []) as string[]).join("\n"));
    setTvRoles(isPlex ? peopleRolesForPlexUiState(tv.preview_include_people_roles) : normalizePeopleRolesFromApi(tv.preview_include_people_roles));
  }, [tv, isPlex]);

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
    setGenreMovies(prunerGenresFromApi(movies.preview_include_genres));
    setYearMinMovies(movies.preview_year_min != null ? String(movies.preview_year_min) : "");
    setYearMaxMovies(movies.preview_year_max != null ? String(movies.preview_year_max) : "");
    setStudioMovies([...(movies.preview_include_studios ?? [])]);
    setMoviesPeople(((movies.preview_include_people ?? []) as string[]).join("\n"));
    setMoviesRoles(
      isPlex ? peopleRolesForPlexUiState(movies.preview_include_people_roles) : normalizePeopleRolesFromApi(movies.preview_include_people_roles),
    );
    setMoviesCollections((movies.preview_include_collections ?? []).join(", "));
  }, [movies, isPlex]);

  function buildFilterPatch(
    scope: "tv" | "movies",
    genres: string[],
    yMinStr: string,
    yMaxStrStr: string,
    studios: string[],
    collectionsText?: string,
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
      preview_include_genres: [...genres],
      preview_year_min: yMinStr.trim() ? yMin : null,
      preview_year_max: yMaxStrStr.trim() ? yMax : null,
      preview_include_studios: [...studios],
      ...(isPlex && scope === "movies" ? { preview_include_collections: parseCommaTokens(collectionsText ?? "") } : {}),
    };
  }

  async function persistTv(): Promise<void> {
    if (!tv) return;
    const csrf_token = await fetchCsrfToken();
    const raw = parseInt(neverTvDays.trim(), 10);
    const neverOn = !isPlex && Number.isFinite(raw) && raw >= 7;
    const neverDays = neverOn ? Math.max(7, Math.min(3650, raw)) : 90;
    const filters = buildFilterPatch("tv", genreTv, yearMinTv, yearMaxTv, studioTv);
    const rolesPersist = isPlex ? peopleRolesForPlexPersist(tvRoles) : [...tvRoles];
    await patchPrunerScope(instanceId, "tv", {
      missing_primary_media_reported_enabled: missingPrimaryTv,
      watched_tv_reported_enabled: watchedTv,
      never_played_stale_reported_enabled: neverOn,
      never_played_min_age_days: neverDays,
      ...filters,
      preview_include_people: parsePeopleLines(tvPeople),
      preview_include_people_roles: rolesPersist,
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
    const filters = buildFilterPatch("movies", genreMovies, yearMinMovies, yearMaxMovies, studioMovies, moviesCollections);
    const rolesPersist = isPlex ? peopleRolesForPlexPersist(moviesRoles) : [...moviesRoles];
    await patchPrunerScope(instanceId, "movies", {
      missing_primary_media_reported_enabled: missingPrimaryMovies,
      watched_movies_reported_enabled: watchedMovies,
      watched_movie_low_rating_reported_enabled: lowOn,
      ...(isPlex
        ? { watched_movie_low_rating_max_plex_audience_rating: cap }
        : { watched_movie_low_rating_max_jellyfin_emby_community_rating: cap }),
      unwatched_movie_stale_reported_enabled: uwOn,
      unwatched_movie_stale_min_age_days: uwDays,
      preview_include_people: parsePeopleLines(moviesPeople),
      preview_include_people_roles: rolesPersist,
      ...filters,
      csrf_token,
    });
    await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
  }

  async function saveTv() {
    if (!tv) return;
    setErrTv(null);
    setMsgTv(null);
    setBusyTv(true);
    try {
      await persistTv();
      setTvRolesCoerceMsg(null);
      setMsgTv("Saved TV settings.");
    } catch (e) {
      setErrTv((e as Error).message);
    } finally {
      setBusyTv(false);
    }
  }

  async function saveMovies() {
    if (!movies) return;
    setErrMovies(null);
    setMsgMovies(null);
    setBusyMovies(true);
    try {
      await persistMovies();
      setMoviesRolesCoerceMsg(null);
      setMsgMovies("Saved Movies settings.");
    } catch (e) {
      setErrMovies((e as Error).message);
    } finally {
      setBusyMovies(false);
    }
  }

  const persistTvRef = useRef(persistTv);
  persistTvRef.current = persistTv;
  const persistMoviesRef = useRef(persistMovies);
  persistMoviesRef.current = persistMovies;
  useImperativeHandle(
    ref,
    () => ({
      ensureTvSaved: () => persistTvRef.current(),
      ensureMoviesSaved: () => persistMoviesRef.current(),
    }),
    [],
  );

  const tvControlsDisabled = !canOperate || busyTv || busyMovies;
  const moviesControlsDisabled = !canOperate || busyTv || busyMovies;
  const saveDisabledTv = busyTv || !canOperate || instanceId <= 0;
  const saveDisabledMovies = busyMovies || !canOperate || instanceId <= 0;

  const narrowingLabelClass = "text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]";

  return (
    <div
      className="mm-card mm-dash-card border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5 sm:p-6"
      data-testid={`pruner-provider-configuration-${provider}`}
      data-provider-section="cleanup"
    >
      <div className="grid gap-8 lg:grid-cols-2 lg:gap-10">
        <fieldset disabled={tvControlsDisabled} className="min-w-0 border-0 p-0">
          <div className="min-w-0 space-y-5" data-testid={`pruner-provider-tv-config-${provider}`}>
            <div className="space-y-1 border-b border-[var(--mm-border)] pb-2">
              <span className="text-sm font-semibold uppercase tracking-wide text-[var(--mm-text1)]">TV</span>
            </div>
            <p className={narrowingLabelClass}>Rules</p>
            {isPlex ? (
              <div
                className="rounded-md border border-amber-600/40 bg-amber-950/20 px-4 py-3 text-sm text-[var(--mm-text)]"
                data-testid="pruner-plex-tv-rules-scope-note"
                role="note"
              >
                <p className="font-semibold text-amber-100">Plex TV — limited options</p>
                <p className="mt-2 text-sm text-[var(--mm-text2)]">
                  {
                    "Plex doesn't provide a watched signal for TV shows, so only the missing poster rule is available here. Watched TV cleanup is not supported on Plex."
                  }
                </p>
              </div>
            ) : null}
            {!isPlex ? (
              <>
                <MmOnOffSwitch
                  id={`pruner-op-tv-watched-${provider}`}
                  label="Delete TV episodes you have already watched"
                  enabled={watchedTv}
                  disabled={tvControlsDisabled}
                  onChange={setWatchedTv}
                />
                <label className="block text-sm text-[var(--mm-text1)]">
                  <span className="mb-1 block text-xs text-[var(--mm-text3)]">
                    Delete TV shows not watched in the last ___ days (0 = off)
                  </span>
                  <input
                    type="number"
                    min={0}
                    max={3650}
                    className="mm-input w-full max-w-xs"
                    value={neverTvDays}
                    onChange={(e) => setNeverTvDays(e.target.value)}
                    disabled={tvControlsDisabled}
                  />
                </label>
              </>
            ) : null}
            <MmOnOffSwitch
              id={`pruner-op-tv-missing-${provider}`}
              label="Delete TV items missing a main poster or episode image"
              enabled={missingPrimaryTv}
              disabled={tvControlsDisabled}
              onChange={setMissingPrimaryTv}
            />

            <div className="border-t border-[var(--mm-border)] pt-4 mt-1">
              <p className="text-xs text-[var(--mm-text3)]">Optional rules — select to activate</p>
            </div>

            <div className="space-y-1">
              <span className="mb-1 block text-xs font-medium text-[var(--mm-text3)]">Genres</span>
              <PrunerGenreMultiSelect
                value={genreTv}
                onChange={setGenreTv}
                disabled={tvControlsDisabled}
                testId={`pruner-rules-genre-tv-${provider}`}
              />
            </div>
            <label className="block text-sm text-[var(--mm-text2)]" data-testid={`pruner-provider-tv-people-${provider}`}>
              <span className="mb-1 block text-xs font-medium text-[var(--mm-text3)]">People</span>
              <textarea
                className="mm-input min-h-[6rem] w-full font-sans text-sm"
                rows={5}
                placeholder="e.g. Alex Carter, Jordan Lee (comma or one per line)"
                value={tvPeople}
                disabled={tvControlsDisabled}
                onChange={(e) => setTvPeople(e.target.value)}
              />
              <span className="mt-1 block text-xs text-[var(--mm-text3)]">Leave empty to skip this rule.</span>
            </label>
            <PrunerPeopleRoleCheckboxes
              value={tvRoles}
              onChange={setTvRoles}
              disabled={tvControlsDisabled}
              variant={isPlex ? "plex" : "emby-jellyfin"}
              coerceCastMsg={tvRolesCoerceMsg}
              onClearCoerceMsg={() => setTvRolesCoerceMsg(null)}
              onCoercedToCast={() =>
                setTvRolesCoerceMsg("At least one role must be selected — defaulting to cast.")
              }
              testId={`pruner-provider-tv-people-roles-${provider}`}
              rolesHeading="Check these credits when matching names"
            />
            <div className="space-y-1">
              <span className="mb-1 block text-xs font-medium text-[var(--mm-text3)]">Studios</span>
              <PrunerStudioMultiSelect
                value={studioTv}
                onChange={setStudioTv}
                disabled={tvControlsDisabled}
                instanceId={instanceId}
                scope="tv"
                testId={`pruner-rules-studio-tv-${provider}`}
              />
            </div>
            <YearRange
              min={yearMinTv}
              max={yearMaxTv}
              onMin={setYearMinTv}
              onMax={setYearMaxTv}
              disabled={tvControlsDisabled}
              title="Release year range"
              helperText="Leave empty to skip this rule."
            />

            <div className="border-t border-[var(--mm-border)] pt-4 mt-1" role="separator" />
            <div className="space-y-3">
              {canOperate ? (
                <button
                  type="button"
                  className={fetcherMenuButtonClass({ variant: "primary", disabled: saveDisabledTv })}
                  disabled={saveDisabledTv}
                  onClick={() => void saveTv()}
                >
                  {busyTv ? "Saving…" : "Save TV settings"}
                </button>
              ) : null}
              {msgTv ? (
                <p className="text-sm text-green-600" role="status">
                  {msgTv}
                </p>
              ) : null}
              {errTv ? (
                <p className="text-sm text-red-500" role="alert">
                  {errTv}
                </p>
              ) : null}
            </div>
          </div>
        </fieldset>

        <fieldset disabled={moviesControlsDisabled} className="min-w-0 border-0 p-0 lg:border-l lg:border-[var(--mm-border)] lg:pl-8">
          <div className="min-w-0 space-y-5" data-testid={`pruner-provider-movies-config-${provider}`}>
            <div className="flex items-center gap-2 border-b border-[var(--mm-border)] pb-2">
              <span className="text-sm font-semibold uppercase tracking-wide text-[var(--mm-text1)]">Movies</span>
            </div>
            <p className={narrowingLabelClass}>Rules</p>
            <MmOnOffSwitch
              id={`pruner-op-mov-watched-${provider}`}
              label="Delete movies you have already watched"
              enabled={watchedMovies}
              disabled={moviesControlsDisabled}
              onChange={setWatchedMovies}
            />
            <label className="block text-sm text-[var(--mm-text1)]" htmlFor={`pruner-op-mov-lowrating-${provider}`}>
              <span className="mb-1 block text-xs text-[var(--mm-text3)]">
                {isPlex
                  ? "Delete watched movies rated below this score — uses Plex audience rating (0–10, 0 = off)"
                  : "Delete watched movies rated below this score — uses your server's community rating (0–10, 0 = off)"}
              </span>
              <input
                id={`pruner-op-mov-lowrating-${provider}`}
                type="number"
                min={0}
                max={10}
                step={0.1}
                className="mm-input w-full max-w-xs"
                value={lowRatingMovies}
                onChange={(e) => setLowRatingMovies(e.target.value)}
                disabled={moviesControlsDisabled}
              />
            </label>
            <label className="block text-sm text-[var(--mm-text2)]">
              <span className="mb-1 block text-xs text-[var(--mm-text3)]">
                Delete movies you have not watched that are older than ___ days (0 = off)
              </span>
              <input
                type="number"
                min={0}
                max={3650}
                className="mm-input w-full max-w-xs"
                value={unwatchedDays}
                onChange={(e) => setUnwatchedDays(e.target.value)}
                disabled={moviesControlsDisabled}
              />
            </label>
            {!isPlex ? (
              <MmOnOffSwitch
                id={`pruner-op-mov-missing-${provider}`}
                label="Delete movies missing a main poster"
                enabled={missingPrimaryMovies}
                disabled={moviesControlsDisabled}
                onChange={setMissingPrimaryMovies}
              />
            ) : null}

            <div className="border-t border-[var(--mm-border)] pt-4 mt-1">
              <p className="text-xs text-[var(--mm-text3)]">Optional rules — select to activate</p>
            </div>

            <div className="space-y-1">
              <span className="mb-1 block text-xs font-medium text-[var(--mm-text3)]">Genres</span>
              <PrunerGenreMultiSelect
                value={genreMovies}
                onChange={setGenreMovies}
                disabled={moviesControlsDisabled}
                testId={`pruner-rules-genre-movies-${provider}`}
              />
            </div>
            <label className="block text-sm text-[var(--mm-text2)]" data-testid={`pruner-provider-movies-people-${provider}`}>
              <span className="mb-1 block text-xs font-medium text-[var(--mm-text3)]">People</span>
              <textarea
                className="mm-input min-h-[6rem] w-full font-sans text-sm"
                rows={5}
                placeholder="e.g. Alex Carter, Jordan Lee (comma or one per line)"
                value={moviesPeople}
                disabled={moviesControlsDisabled}
                onChange={(e) => setMoviesPeople(e.target.value)}
              />
              <span className="mt-1 block text-xs text-[var(--mm-text3)]">Leave empty to skip this rule.</span>
            </label>
            <PrunerPeopleRoleCheckboxes
              value={moviesRoles}
              onChange={setMoviesRoles}
              disabled={moviesControlsDisabled}
              variant={isPlex ? "plex" : "emby-jellyfin"}
              coerceCastMsg={moviesRolesCoerceMsg}
              onClearCoerceMsg={() => setMoviesRolesCoerceMsg(null)}
              onCoercedToCast={() =>
                setMoviesRolesCoerceMsg("At least one role must be selected — defaulting to cast.")
              }
              testId={`pruner-provider-movies-people-roles-${provider}`}
              rolesHeading="Check these credits when matching names"
            />
            <div className="space-y-1">
              <span className="mb-1 block text-xs font-medium text-[var(--mm-text3)]">Studios</span>
              <PrunerStudioMultiSelect
                value={studioMovies}
                onChange={setStudioMovies}
                disabled={moviesControlsDisabled}
                instanceId={instanceId}
                scope="movies"
                testId={`pruner-rules-studio-movies-${provider}`}
              />
            </div>
            <YearRange
              min={yearMinMovies}
              max={yearMaxMovies}
              onMin={setYearMinMovies}
              onMax={setYearMaxMovies}
              disabled={moviesControlsDisabled}
              title="Release year range"
              helperText="Leave empty to skip this rule."
            />
            {isPlex ? (
              <CommaField
                label="Collections"
                placeholder="e.g. MCU, Pixar"
                helper="Optional scope metadata — no preview rule reads collections in this release."
                value={moviesCollections}
                onChange={setMoviesCollections}
                disabled={moviesControlsDisabled}
              />
            ) : null}

            <div className="border-t border-[var(--mm-border)] pt-4 mt-1" role="separator" />
            <div className="space-y-3">
              {canOperate ? (
                <button
                  type="button"
                  className={fetcherMenuButtonClass({ variant: "primary", disabled: saveDisabledMovies })}
                  disabled={saveDisabledMovies}
                  onClick={() => void saveMovies()}
                >
                  {busyMovies ? "Saving…" : "Save Movies settings"}
                </button>
              ) : null}
              {msgMovies ? (
                <p className="text-sm text-green-600" role="status">
                  {msgMovies}
                </p>
              ) : null}
              {errMovies ? (
                <p className="text-sm text-red-500" role="alert">
                  {errMovies}
                </p>
              ) : null}
            </div>
          </div>
        </fieldset>
      </div>
    </div>
  );
  },
);

/**
 * People controls were merged into {@link PrunerProviderRulesCard}. Kept as a no-op export for compatibility with
 * older tests or imports; nothing in the app tree renders this component.
 */
export function PrunerProviderPeopleCard() {
  return null;
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
  helperText,
  title,
}: {
  min: string;
  max: string;
  onMin: (v: string) => void;
  onMax: (v: string) => void;
  disabled: boolean;
  helperText?: string;
  /** Section label above min/max inputs (default: year range). */
  title?: string;
}) {
  return (
    <div className="space-y-1">
      <span className="text-xs font-medium text-[var(--mm-text3)]">{title ?? "Only these years"}</span>
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
      <p className="text-xs text-[var(--mm-text3)]">{helperText ?? "Leave blank for all years."}</p>
    </div>
  );
}
