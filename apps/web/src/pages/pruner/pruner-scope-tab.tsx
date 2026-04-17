import type { ReactNode } from "react";
import { Fragment, useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchCsrfToken } from "../../lib/api/auth-api";
import { useMeQuery } from "../../lib/auth/queries";
import {
  RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
  RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED,
  RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED,
  RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED,
  RULE_FAMILY_WATCHED_MOVIES_REPORTED,
  RULE_FAMILY_WATCHED_TV_REPORTED,
  fetchPrunerApplyEligibility,
  fetchPrunerPreviewRun,
  fetchPrunerPreviewRuns,
  patchPrunerScope,
  postPrunerApplyFromPreview,
  postPrunerPreview,
  prunerApplyLabelForRuleFamily,
} from "../../lib/pruner/api";
import type { PrunerServerInstance } from "../../lib/pruner/api";
import { fetcherMenuButtonClass } from "../fetcher/fetcher-menu-button";
import { formatPrunerDateTime, previewRunRowCaption } from "./pruner-ui-utils";

type Ctx = { instanceId: number; instance: PrunerServerInstance | undefined };

function canApplyFromPreviewSnapshot(
  provider: string | undefined,
  row: { outcome: string; candidate_count: number; rule_family_id: string },
): boolean {
  if (!provider || row.outcome !== "success" || row.candidate_count <= 0) return false;
  if (provider === "jellyfin" || provider === "emby") return true;
  return provider === "plex" && row.rule_family_id === RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED;
}

export function PrunerScopeTab(props: {
  scope: "tv" | "movies";
  contextOverride?: Ctx;
  disabledMode?: boolean;
  /** Flat provider workspace: full-width, schedule on-page, no preview history table. */
  variant?: "default" | "provider";
  /** When variant is provider, selects one subsection (Rules / Filters / Schedule). */
  providerSubSection?: "rules" | "filters" | "schedule";
}) {
  const outletCtx = useOutletContext<Ctx>();
  const { instanceId, instance } = props.contextOverride ?? outletCtx;
  const me = useMeQuery();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [jsonPreview, setJsonPreview] = useState<string | null>(null);
  const [schedEnabled, setSchedEnabled] = useState(false);
  const [schedInterval, setSchedInterval] = useState(3600);
  const [schedMsg, setSchedMsg] = useState<string | null>(null);
  const [applyModalRunId, setApplyModalRunId] = useState<string | null>(null);
  const [applySnapshotConfirmed, setApplySnapshotConfirmed] = useState(false);
  const [staleNeverEnabled, setStaleNeverEnabled] = useState(false);
  const [staleNeverDays, setStaleNeverDays] = useState(90);
  const [staleNeverMsg, setStaleNeverMsg] = useState<string | null>(null);
  const [watchedTvEnabled, setWatchedTvEnabled] = useState(false);
  const [watchedTvMsg, setWatchedTvMsg] = useState<string | null>(null);
  const [watchedMoviesEnabled, setWatchedMoviesEnabled] = useState(false);
  const [watchedMoviesMsg, setWatchedMoviesMsg] = useState<string | null>(null);
  const [lowRatingEnabled, setLowRatingEnabled] = useState(false);
  const [lowRatingMax, setLowRatingMax] = useState("4");
  const [lowRatingMsg, setLowRatingMsg] = useState<string | null>(null);
  const [unwatchedStaleEnabled, setUnwatchedStaleEnabled] = useState(false);
  const [unwatchedStaleDays, setUnwatchedStaleDays] = useState(90);
  const [unwatchedStaleMsg, setUnwatchedStaleMsg] = useState<string | null>(null);
  const [genreText, setGenreText] = useState("");
  const [genreMsg, setGenreMsg] = useState<string | null>(null);
  const [peopleText, setPeopleText] = useState("");
  const [peopleMsg, setPeopleMsg] = useState<string | null>(null);
  const [yearMinStr, setYearMinStr] = useState("");
  const [yearMaxStr, setYearMaxStr] = useState("");
  const [yearMsg, setYearMsg] = useState<string | null>(null);
  const [studioText, setStudioText] = useState("");
  const [studioMsg, setStudioMsg] = useState<string | null>(null);
  const [collectionText, setCollectionText] = useState("");
  const [collectionMsg, setCollectionMsg] = useState<string | null>(null);
  const [previewMaxItems, setPreviewMaxItems] = useState(500);
  const [previewMaxItemsMsg, setPreviewMaxItemsMsg] = useState<string | null>(null);
  const [bundleMsg, setBundleMsg] = useState<string | null>(null);
  const isProvider = props.variant === "provider";
  const provSub = props.providerSubSection;
  const canOperate = me.data?.role === "admin" || me.data?.role === "operator";
  const showInteractiveControls = canOperate || Boolean(props.disabledMode);

  const scopeRow = instance?.scopes.find((s) => s.media_scope === props.scope);
  const label = props.scope === "tv" ? "TV (episodes)" : "Movies (one row per movie item)";
  const isPlex = instance?.provider === "plex";
  const sectionWord = isProvider ? "scope" : "tab";

  function ruleFamilyColumnLabel(id: string): string {
    if (id === RULE_FAMILY_WATCHED_TV_REPORTED) return "Watched TV (episodes)";
    if (id === RULE_FAMILY_WATCHED_MOVIES_REPORTED) return "Watched movies";
    if (id === RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED) return "Watched low-rating movies";
    if (id === RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED) return "Unwatched stale movies";
    if (id === RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED) return "Stale never-played";
    if (id === RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED) return "Missing primary art";
    return id;
  }

  const previewRunsQueryKey = ["pruner", "preview-runs", instanceId, props.scope] as const;
  const runsQuery = useQuery({
    queryKey: previewRunsQueryKey,
    queryFn: () => fetchPrunerPreviewRuns(instanceId, { media_scope: props.scope, limit: 25 }),
    enabled: !isProvider && Boolean(instanceId),
  });

  const applyEligQuery = useQuery({
    queryKey: ["pruner", "apply-eligibility", instanceId, props.scope, applyModalRunId] as const,
    queryFn: () => fetchPrunerApplyEligibility(instanceId, props.scope, applyModalRunId!),
    enabled: Boolean(instanceId && applyModalRunId),
  });

  const applySnapshotOperatorLabel = applyEligQuery.data
    ? applyEligQuery.data.apply_operator_label ||
      prunerApplyLabelForRuleFamily(applyEligQuery.data.rule_family_id)
    : null;

  useEffect(() => {
    if (!scopeRow) return;
    setSchedEnabled(scopeRow.scheduled_preview_enabled);
    setSchedInterval(scopeRow.scheduled_preview_interval_seconds);
    setStaleNeverEnabled(scopeRow.never_played_stale_reported_enabled);
    setStaleNeverDays(scopeRow.never_played_min_age_days);
    setWatchedTvEnabled(scopeRow.watched_tv_reported_enabled);
    setWatchedMoviesEnabled(scopeRow.watched_movies_reported_enabled);
    setLowRatingEnabled(scopeRow.watched_movie_low_rating_reported_enabled);
    setLowRatingMax(
      String(
        isPlex
          ? scopeRow.watched_movie_low_rating_max_plex_audience_rating
          : scopeRow.watched_movie_low_rating_max_jellyfin_emby_community_rating,
      ),
    );
    setUnwatchedStaleEnabled(scopeRow.unwatched_movie_stale_reported_enabled);
    setUnwatchedStaleDays(scopeRow.unwatched_movie_stale_min_age_days);
    setGenreText((scopeRow.preview_include_genres ?? []).join(", "));
    setPeopleText((scopeRow.preview_include_people ?? []).join(", "));
    setYearMinStr(scopeRow.preview_year_min != null ? String(scopeRow.preview_year_min) : "");
    setYearMaxStr(scopeRow.preview_year_max != null ? String(scopeRow.preview_year_max) : "");
    setStudioText((scopeRow.preview_include_studios ?? []).join(", "));
    setCollectionText((scopeRow.preview_include_collections ?? []).join(", "));
    setPreviewMaxItems(scopeRow.preview_max_items);
  }, [
    scopeRow?.scheduled_preview_enabled,
    scopeRow?.scheduled_preview_interval_seconds,
    scopeRow?.never_played_stale_reported_enabled,
    scopeRow?.never_played_min_age_days,
    scopeRow?.watched_tv_reported_enabled,
    scopeRow?.watched_movies_reported_enabled,
    scopeRow?.watched_movie_low_rating_reported_enabled,
    scopeRow?.watched_movie_low_rating_max_jellyfin_emby_community_rating,
    scopeRow?.watched_movie_low_rating_max_plex_audience_rating,
    isPlex,
    scopeRow?.unwatched_movie_stale_reported_enabled,
    scopeRow?.unwatched_movie_stale_min_age_days,
    scopeRow?.preview_include_genres,
    scopeRow?.preview_include_people,
    scopeRow?.preview_year_min,
    scopeRow?.preview_year_max,
    scopeRow?.preview_include_studios,
    scopeRow?.preview_include_collections,
    scopeRow?.preview_max_items,
    scopeRow?.media_scope,
    instanceId,
  ]);

  async function saveSchedule() {
    setSchedMsg(null);
    setErr(null);
    setBusy(true);
    try {
      const csrf_token = await fetchCsrfToken();
      const iv = Math.max(60, Math.min(86400, Number(schedInterval) || 3600));
      await patchPrunerScope(instanceId, props.scope, {
        scheduled_preview_enabled: schedEnabled,
        scheduled_preview_interval_seconds: iv,
        csrf_token,
      });
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      setSchedMsg(
        `Saved. This schedule applies only to this server and this ${sectionWord} (TV or Movies).`,
      );
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function savePreviewMaxItemsSettings() {
    setPreviewMaxItemsMsg(null);
    setErr(null);
    setBusy(true);
    try {
      const csrf_token = await fetchCsrfToken();
      const v = Math.max(1, Math.min(5000, Number(previewMaxItems) || 500));
      await patchPrunerScope(instanceId, props.scope, {
        preview_max_items: v,
        csrf_token,
      });
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      setPreviewMaxItemsMsg("Saved preview cap for this scope.");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function saveStaleNeverSettings() {
    setStaleNeverMsg(null);
    setErr(null);
    setBusy(true);
    try {
      const csrf_token = await fetchCsrfToken();
      const d = Math.max(7, Math.min(3650, Number(staleNeverDays) || 90));
      await patchPrunerScope(instanceId, props.scope, {
        never_played_stale_reported_enabled: staleNeverEnabled,
        never_played_min_age_days: d,
        csrf_token,
      });
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      setStaleNeverMsg("Saved never-played rule settings for this scope.");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function saveGenreFilters() {
    setGenreMsg(null);
    setErr(null);
    setBusy(true);
    try {
      const csrf_token = await fetchCsrfToken();
      const tokens = genreText
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      await patchPrunerScope(instanceId, props.scope, {
        preview_include_genres: tokens,
        csrf_token,
      });
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      setGenreMsg(
        tokens.length
          ? "Saved genre filters for this scope."
          : "Cleared genre filters for this scope.",
      );
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function savePeopleFilters() {
    setPeopleMsg(null);
    setErr(null);
    setBusy(true);
    try {
      const csrf_token = await fetchCsrfToken();
      const tokens = peopleText
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      await patchPrunerScope(instanceId, props.scope, {
        preview_include_people: tokens,
        csrf_token,
      });
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      setPeopleMsg(
        tokens.length
          ? "Saved people filters for this scope."
          : "Cleared people filters for this scope.",
      );
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function savePreviewYearBounds() {
    setYearMsg(null);
    setErr(null);
    setBusy(true);
    try {
      const csrf_token = await fetchCsrfToken();
      const parseBound = (raw: string): number | null | "bad" => {
        const t = raw.trim();
        if (!t) return null;
        const n = Number(t);
        if (!Number.isInteger(n) || n < 1900 || n > 2100) return "bad";
        return n;
      };
      const yMin = parseBound(yearMinStr);
      const yMax = parseBound(yearMaxStr);
      if (yMin === "bad" || yMax === "bad") {
        setErr("Each year must be a whole number between 1900 and 2100, or left empty.");
        return;
      }
      if (yMin != null && yMax != null && yMin > yMax) {
        setErr("Minimum year must be less than or equal to maximum year.");
        return;
      }
      await patchPrunerScope(instanceId, props.scope, {
        preview_year_min: yearMinStr.trim() ? yMin : null,
        preview_year_max: yearMaxStr.trim() ? yMax : null,
        csrf_token,
      });
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      setYearMsg(
        "Saved preview year bounds for this scope.",
      );
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function saveStudioPreviewFilters() {
    setStudioMsg(null);
    setErr(null);
    setBusy(true);
    try {
      const csrf_token = await fetchCsrfToken();
      const tokens = studioText
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      await patchPrunerScope(instanceId, props.scope, {
        preview_include_studios: tokens,
        csrf_token,
      });
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      setStudioMsg(
        tokens.length
          ? "Saved studio filters for this scope."
          : "Cleared studio filters for this scope.",
      );
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function saveCollectionPreviewFilters() {
    setCollectionMsg(null);
    setErr(null);
    setBusy(true);
    try {
      const csrf_token = await fetchCsrfToken();
      const tokens = collectionText
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      await patchPrunerScope(instanceId, props.scope, {
        preview_include_collections: tokens,
        csrf_token,
      });
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      setCollectionMsg(
        tokens.length
          ? "Saved collection filters for this scope."
          : "Cleared collection filters for this scope.",
      );
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function saveWatchedMoviesSettings() {
    setWatchedMoviesMsg(null);
    setErr(null);
    setBusy(true);
    try {
      const csrf_token = await fetchCsrfToken();
      await patchPrunerScope(instanceId, props.scope, {
        watched_movies_reported_enabled: watchedMoviesEnabled,
        csrf_token,
      });
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      setWatchedMoviesMsg("Saved watched movies rule for this scope.");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function saveLowRatingMovieSettings() {
    setLowRatingMsg(null);
    setErr(null);
    setBusy(true);
    try {
      const csrf_token = await fetchCsrfToken();
      const cap = Math.max(0, Math.min(10, Number.parseFloat(lowRatingMax) || 4));
      await patchPrunerScope(instanceId, props.scope, {
        watched_movie_low_rating_reported_enabled: lowRatingEnabled,
        ...(instance?.provider === "plex"
          ? { watched_movie_low_rating_max_plex_audience_rating: cap }
          : { watched_movie_low_rating_max_jellyfin_emby_community_rating: cap }),
        csrf_token,
      });
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      setLowRatingMsg(
        instance?.provider === "plex"
          ? "Saved watched low-rating rule (Plex audienceRating ceiling)."
          : "Saved watched low-rating rule (CommunityRating ceiling).",
      );
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function saveUnwatchedStaleMovieSettings() {
    setUnwatchedStaleMsg(null);
    setErr(null);
    setBusy(true);
    try {
      const csrf_token = await fetchCsrfToken();
      const d = Math.max(7, Math.min(3650, Number(unwatchedStaleDays) || 90));
      await patchPrunerScope(instanceId, props.scope, {
        unwatched_movie_stale_reported_enabled: unwatchedStaleEnabled,
        unwatched_movie_stale_min_age_days: d,
        csrf_token,
      });
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      setUnwatchedStaleMsg(
        instance?.provider === "plex"
          ? "Saved unwatched stale movies rule for this scope (Plex addedAt age)."
          : "Saved unwatched stale movies rule for this scope (DateCreated age).",
      );
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function saveWatchedTvSettings() {
    setWatchedTvMsg(null);
    setErr(null);
    setBusy(true);
    try {
      const csrf_token = await fetchCsrfToken();
      await patchPrunerScope(instanceId, props.scope, {
        watched_tv_reported_enabled: watchedTvEnabled,
        csrf_token,
      });
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      setWatchedTvMsg("Saved watched TV rule for this scope.");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function runPreview() {
    setErr(null);
    setBusy(true);
    setPreview(null);
    try {
      const { pruner_job_id } = await postPrunerPreview(instanceId, props.scope);
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      await qc.invalidateQueries({ queryKey: previewRunsQueryKey });
      setPreview(
        `Queued missing-primary preview job #${pruner_job_id}. When the worker finishes, the summary above and the recent-run table update automatically (this scope only).`,
      );
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function runStaleNeverPreview() {
    setErr(null);
    setBusy(true);
    setPreview(null);
    try {
      const { pruner_job_id } = await postPrunerPreview(instanceId, props.scope, {
        rule_family_id: RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED,
      });
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      await qc.invalidateQueries({ queryKey: previewRunsQueryKey });
      setPreview(
        `Queued never-played stale preview job #${pruner_job_id}. When the worker finishes, the table below updates (this scope only).`,
      );
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function runWatchedMoviesPreview() {
    setErr(null);
    setBusy(true);
    setPreview(null);
    try {
      const { pruner_job_id } = await postPrunerPreview(instanceId, props.scope, {
        rule_family_id: RULE_FAMILY_WATCHED_MOVIES_REPORTED,
      });
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      await qc.invalidateQueries({ queryKey: previewRunsQueryKey });
      setPreview(
        `Queued watched movies preview job #${pruner_job_id}. When the worker finishes, the table below updates (this Movies tab and instance only).`,
      );
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function runLowRatingMoviesPreview() {
    setErr(null);
    setBusy(true);
    setPreview(null);
    try {
      const { pruner_job_id } = await postPrunerPreview(instanceId, props.scope, {
        rule_family_id: RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED,
      });
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      await qc.invalidateQueries({ queryKey: previewRunsQueryKey });
      setPreview(
        `Queued watched low-rating movies preview job #${pruner_job_id}. When the worker finishes, the table below updates (this Movies tab and instance only).`,
      );
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function runUnwatchedStaleMoviesPreview() {
    setErr(null);
    setBusy(true);
    setPreview(null);
    try {
      const { pruner_job_id } = await postPrunerPreview(instanceId, props.scope, {
        rule_family_id: RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED,
      });
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      await qc.invalidateQueries({ queryKey: previewRunsQueryKey });
      setPreview(
        `Queued unwatched stale movies preview job #${pruner_job_id}. When the worker finishes, the table below updates (this Movies tab and instance only).`,
      );
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function runWatchedTvPreview() {
    setErr(null);
    setBusy(true);
    setPreview(null);
    try {
      const { pruner_job_id } = await postPrunerPreview(instanceId, props.scope, {
        rule_family_id: RULE_FAMILY_WATCHED_TV_REPORTED,
      });
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      await qc.invalidateQueries({ queryKey: previewRunsQueryKey });
      setPreview(
        `Queued watched TV preview job #${pruner_job_id}. When the worker finishes, the table below updates (this TV tab and instance only).`,
      );
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function openApplyModal(runUuid: string) {
    setApplySnapshotConfirmed(false);
    setApplyModalRunId(runUuid);
  }

  function closeApplyModal() {
    setApplyModalRunId(null);
    setApplySnapshotConfirmed(false);
  }

  async function confirmApplyFromSnapshot() {
    if (!applyModalRunId) return;
    const runId = applyModalRunId;
    const elig = applyEligQuery.data;
    if (!elig) return;
    const opLabel =
      elig.apply_operator_label || prunerApplyLabelForRuleFamily(elig.rule_family_id);
    setErr(null);
    setBusy(true);
    try {
      const { pruner_job_id } = await postPrunerApplyFromPreview(instanceId, props.scope, runId);
      await qc.invalidateQueries({ queryKey: previewRunsQueryKey });
      await qc.invalidateQueries({ queryKey: ["activity"] });
      closeApplyModal();
      setPreview(
        `Queued ${opLabel.toLowerCase()} job #${pruner_job_id} for preview snapshot ${runId.slice(0, 8)}… (this preview only; worker runs separately).`,
      );
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function loadJsonFor(runUuid?: string | null) {
    const uuid = runUuid ?? scopeRow?.last_preview_run_uuid;
    if (!uuid) {
      setErr("No preview run selected.");
      return;
    }
    setErr(null);
    setBusy(true);
    setJsonPreview(null);
    try {
      const run = await fetchPrunerPreviewRun(instanceId, uuid);
      setJsonPreview(run.candidates_json);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function saveProviderTvRulesBundle() {
    setBundleMsg(null);
    setErr(null);
    setBusy(true);
    try {
      if (isPlex && props.scope === "tv") {
        setBundleMsg("No TV rules to save for Plex.");
        return;
      }
      const csrf_token = await fetchCsrfToken();
      const d = Math.max(7, Math.min(3650, Number(staleNeverDays) || 90));
      await patchPrunerScope(instanceId, "tv", {
        never_played_stale_reported_enabled: staleNeverEnabled,
        never_played_min_age_days: d,
        watched_tv_reported_enabled: watchedTvEnabled,
        csrf_token,
      });
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      setBundleMsg("Saved TV rules.");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function saveProviderMoviesRulesBundle() {
    if (props.scope !== "movies") return;
    setBundleMsg(null);
    setErr(null);
    setBusy(true);
    try {
      const csrf_token = await fetchCsrfToken();
      const cap = Math.max(0, Math.min(10, Number.parseFloat(lowRatingMax) || 4));
      const d = Math.max(7, Math.min(3650, Number(unwatchedStaleDays) || 90));
      await patchPrunerScope(instanceId, "movies", {
        watched_movies_reported_enabled: watchedMoviesEnabled,
        watched_movie_low_rating_reported_enabled: lowRatingEnabled,
        ...(instance?.provider === "plex"
          ? { watched_movie_low_rating_max_plex_audience_rating: cap }
          : { watched_movie_low_rating_max_jellyfin_emby_community_rating: cap }),
        unwatched_movie_stale_reported_enabled: unwatchedStaleEnabled,
        unwatched_movie_stale_min_age_days: d,
        csrf_token,
      });
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      setBundleMsg("Saved Movies rules.");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function saveProviderFiltersBundle() {
    setBundleMsg(null);
    setErr(null);
    setBusy(true);
    try {
      const csrf_token = await fetchCsrfToken();
      const genreTokens = genreText
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const peopleTokens = peopleText
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const studioTokens = studioText
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const parseBound = (raw: string): number | null | "bad" => {
        const t = raw.trim();
        if (!t) return null;
        const n = Number(t);
        if (!Number.isInteger(n) || n < 1900 || n > 2100) return "bad";
        return n;
      };
      const yMin = parseBound(yearMinStr);
      const yMax = parseBound(yearMaxStr);
      if (yMin === "bad" || yMax === "bad") {
        setErr("Each year must be a whole number between 1900 and 2100, or left empty.");
        return;
      }
      if (yMin != null && yMax != null && yMin > yMax) {
        setErr("Minimum year must be less than or equal to maximum year.");
        return;
      }
      const basePayload = {
        preview_include_genres: genreTokens,
        preview_include_people: peopleTokens,
        preview_year_min: yearMinStr.trim() ? yMin : null,
        preview_year_max: yearMaxStr.trim() ? yMax : null,
        preview_include_studios: studioTokens,
        csrf_token,
      };
      if (isPlex && props.scope === "movies") {
        const collTokens = collectionText
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean);
        await patchPrunerScope(instanceId, props.scope, {
          ...basePayload,
          preview_include_collections: collTokens,
        });
      } else {
        await patchPrunerScope(instanceId, props.scope, basePayload);
      }
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      setBundleMsg(props.scope === "tv" ? "Saved TV filters." : "Saved Movies filters.");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function saveProviderScheduleBundle() {
    setBundleMsg(null);
    setSchedMsg(null);
    setPreviewMaxItemsMsg(null);
    setErr(null);
    setBusy(true);
    try {
      const csrf_token = await fetchCsrfToken();
      const iv = Math.max(60, Math.min(86400, Number(schedInterval) || 3600));
      const cap = Math.max(1, Math.min(5000, Number(previewMaxItems) || 500));
      await patchPrunerScope(instanceId, props.scope, {
        preview_max_items: cap,
        scheduled_preview_enabled: schedEnabled,
        scheduled_preview_interval_seconds: iv,
        csrf_token,
      });
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      setBundleMsg(
        props.scope === "tv" ? "Saved TV schedule and limits." : "Saved Movies schedule and limits.",
      );
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function renderProviderRulesControls(): ReactNode {
    if (props.scope === "tv") {
      if (isPlex) {
        return (
          <div className="space-y-6" data-testid="pruner-provider-plex-tv-unsupported-rules">
            <div className="space-y-1.5">
              <p className="text-sm font-medium text-[var(--mm-text1)]">Watched TV removal</p>
              <p className="text-xs leading-relaxed text-[var(--mm-text3)]">Not supported for Plex.</p>
            </div>
            <div className="space-y-1.5">
              <p className="text-sm font-medium text-[var(--mm-text1)]">Never-played TV older than N days</p>
              <p className="text-xs leading-relaxed text-[var(--mm-text3)]">Not supported for Plex.</p>
            </div>
          </div>
        );
      }
      return (
        <div className="space-y-8">
          <div className="space-y-2" data-testid="pruner-never-played-stale-panel">
            <p className="text-sm font-medium text-[var(--mm-text1)]">Never-played TV older than N days</p>
            <p className="text-xs leading-relaxed text-[var(--mm-text3)]">Never played and older than this age.</p>
            {showInteractiveControls ? (
              <div className="space-y-3">
                <label className="flex items-center gap-2 text-sm text-[var(--mm-text)]">
                  <input
                    type="checkbox"
                    checked={staleNeverEnabled}
                    disabled={busy}
                    onChange={(e) => setStaleNeverEnabled(e.target.checked)}
                  />
                  Enable never-played TV older-than rule
                </label>
                <label className="block text-sm text-[var(--mm-text2)]">
                  <span className="mb-1 block text-xs text-[var(--mm-text3)]">Minimum age (days, 7–3650)</span>
                  <input
                    type="number"
                    min={7}
                    max={3650}
                    className="mm-input w-28"
                    value={staleNeverDays}
                    disabled={busy}
                    onChange={(e) => setStaleNeverDays(parseInt(e.target.value, 10) || 90)}
                  />
                </label>
              </div>
            ) : (
              <p className="text-xs text-[var(--mm-text2)]">
                Rule is <strong>{scopeRow?.never_played_stale_reported_enabled ? "on" : "off"}</strong>
                {scopeRow ? <> (minimum age {scopeRow.never_played_min_age_days} days).</> : null}
              </p>
            )}
          </div>
          <div className="space-y-2" data-testid="pruner-watched-tv-panel">
            <p className="text-sm font-medium text-[var(--mm-text1)]">Watched TV removal</p>
            <p className="text-xs leading-relaxed text-[var(--mm-text3)]">
              Delete items marked watched for this provider user.
            </p>
            {showInteractiveControls ? (
              <label className="flex items-center gap-2 text-sm text-[var(--mm-text)]">
                <input
                  type="checkbox"
                  checked={watchedTvEnabled}
                  disabled={busy}
                  onChange={(e) => setWatchedTvEnabled(e.target.checked)}
                />
                Enable watched TV rule
              </label>
            ) : (
              <p className="text-xs text-[var(--mm-text2)]">
                Watched TV rule is <strong>{scopeRow?.watched_tv_reported_enabled ? "on" : "off"}</strong>.
              </p>
            )}
          </div>
        </div>
      );
    }
    return (
      <div className="space-y-8">
        <div className="space-y-2" data-testid="pruner-watched-movies-panel">
          <p className="text-sm font-medium text-[var(--mm-text1)]">Watched movies removal</p>
          <p className="text-xs leading-relaxed text-[var(--mm-text3)]">
            {isPlex ? "Uses Plex watched state from allLeaves." : "Uses provider watched state for movie items."}
          </p>
          {showInteractiveControls ? (
            <label className="flex items-center gap-2 text-sm text-[var(--mm-text)]">
              <input
                type="checkbox"
                checked={watchedMoviesEnabled}
                disabled={busy}
                onChange={(e) => setWatchedMoviesEnabled(e.target.checked)}
              />
              Enable watched movies rule
            </label>
          ) : (
            <p className="text-xs text-[var(--mm-text2)]">
              Watched movies rule is <strong>{scopeRow?.watched_movies_reported_enabled ? "on" : "off"}</strong>.
            </p>
          )}
        </div>
        <div className="space-y-2" data-testid="pruner-watched-low-rating-panel">
          <p className="text-sm font-medium text-[var(--mm-text1)]">Low-rating watched movies</p>
          <p className="text-xs leading-relaxed text-[var(--mm-text3)]">
            {isPlex
              ? "Uses Plex audienceRating; set a maximum rating ceiling."
              : "Uses Jellyfin/Emby CommunityRating; set a maximum rating ceiling."}
          </p>
          {showInteractiveControls ? (
            <div className="space-y-3">
              <label className="flex items-center gap-2 text-sm text-[var(--mm-text)]">
                <input
                  type="checkbox"
                  checked={lowRatingEnabled}
                  disabled={busy}
                  onChange={(e) => setLowRatingEnabled(e.target.checked)}
                />
                Enable low-rating watched movies rule
              </label>
              <label className="block text-sm text-[var(--mm-text2)]">
                <span className="mb-1 block text-xs text-[var(--mm-text3)]">
                  {isPlex ? "Plex audienceRating — max ceiling (0–10)" : "Jellyfin/Emby CommunityRating — max ceiling (0–10)"}
                </span>
                <input
                  type="number"
                  min={0}
                  max={10}
                  step="0.1"
                  className="mm-input w-28"
                  value={lowRatingMax}
                  disabled={busy}
                  onChange={(e) => setLowRatingMax(e.target.value)}
                />
              </label>
            </div>
          ) : (
            <p className="text-xs text-[var(--mm-text2)]">
              Low-rating rule is <strong>{scopeRow?.watched_movie_low_rating_reported_enabled ? "on" : "off"}</strong>.
            </p>
          )}
        </div>
        <div className="space-y-2" data-testid="pruner-unwatched-stale-panel">
          <p className="text-sm font-medium text-[var(--mm-text1)]">Unwatched movies older than N days</p>
          <p className="text-xs leading-relaxed text-[var(--mm-text3)]">
            {isPlex ? "Unwatched + addedAt age." : "Never-played + DateCreated age."}
          </p>
          {showInteractiveControls ? (
            <div className="space-y-3">
              <label className="flex items-center gap-2 text-sm text-[var(--mm-text)]">
                <input
                  type="checkbox"
                  checked={unwatchedStaleEnabled}
                  disabled={busy}
                  onChange={(e) => setUnwatchedStaleEnabled(e.target.checked)}
                />
                Enable unwatched stale movies rule
              </label>
              <label className="block text-sm text-[var(--mm-text2)]">
                <span className="mb-1 block text-xs text-[var(--mm-text3)]">Minimum age (days, 7–3650)</span>
                <input
                  type="number"
                  min={7}
                  max={3650}
                  className="mm-input w-28"
                  value={unwatchedStaleDays}
                  disabled={busy}
                  onChange={(e) => setUnwatchedStaleDays(parseInt(e.target.value, 10) || 90)}
                />
              </label>
            </div>
          ) : (
            <p className="text-xs text-[var(--mm-text2)]">
              Unwatched stale rule is <strong>{scopeRow?.unwatched_movie_stale_reported_enabled ? "on" : "off"}</strong>
              {scopeRow ? <> (min age {scopeRow.unwatched_movie_stale_min_age_days} days).</> : null}
            </p>
          )}
        </div>
        {isPlex ? (
          <p className="text-xs text-[var(--mm-text3)]" data-testid="pruner-plex-other-rules-note" role="status">
            Plex: watched TV and never-played stale are unsupported on the TV scope.
          </p>
        ) : null}
      </div>
    );
  }

  function renderProviderFiltersControls(): ReactNode {
    return (
      <div className="space-y-8">
        {isPlex && props.scope === "tv" ? (
          <p className="text-xs leading-relaxed text-amber-100/90" data-testid="pruner-plex-tv-filters-scope-note" role="status">
            On Plex TV, genre, people, year, and studio filters apply to the <strong>missing primary art</strong> preview
            rule only.
          </p>
        ) : null}
        <div className="space-y-2" data-testid="pruner-genre-filters-panel">
          <p className="text-sm font-medium text-[var(--mm-text1)]">Genre filter</p>
          <p className="text-xs text-[var(--mm-text3)]">Comma-separated genres.</p>
          {showInteractiveControls ? (
            <input
              type="text"
              className="mm-input w-full"
              placeholder="e.g. Drama, Science Fiction"
              value={genreText}
              disabled={busy}
              onChange={(e) => setGenreText(e.target.value)}
            />
          ) : (
            <p className="text-xs text-[var(--mm-text2)]">
              {(scopeRow?.preview_include_genres ?? []).join(", ") || "none"}
            </p>
          )}
        </div>
        <div className="space-y-2" data-testid="pruner-people-filters-panel">
          <p className="text-sm font-medium text-[var(--mm-text1)]">People filter</p>
          <p className="text-xs text-[var(--mm-text3)]">Comma-separated full names.</p>
          {showInteractiveControls ? (
            <input
              type="text"
              className="mm-input w-full"
              placeholder="e.g. Jane Doe, Alan Smithee"
              value={peopleText}
              disabled={busy}
              onChange={(e) => setPeopleText(e.target.value)}
            />
          ) : (
            <p className="text-xs text-[var(--mm-text2)]">
              {(scopeRow?.preview_include_people ?? []).join(", ") || "none"}
            </p>
          )}
        </div>
        <div className="space-y-2" data-testid="pruner-year-filters-panel">
          <p className="text-sm font-medium text-[var(--mm-text1)]">Year range</p>
          <p className="text-xs text-[var(--mm-text3)]">Inclusive 1900–2100. Blank means open-ended.</p>
          {showInteractiveControls ? (
            <div className="flex flex-wrap gap-4">
              <label className="block text-sm text-[var(--mm-text2)]">
                <span className="mb-1 block text-xs text-[var(--mm-text3)]">Min year</span>
                <input
                  type="number"
                  min={1900}
                  max={2100}
                  className="mm-input w-28"
                  value={yearMinStr}
                  disabled={busy}
                  onChange={(e) => setYearMinStr(e.target.value)}
                />
              </label>
              <label className="block text-sm text-[var(--mm-text2)]">
                <span className="mb-1 block text-xs text-[var(--mm-text3)]">Max year</span>
                <input
                  type="number"
                  min={1900}
                  max={2100}
                  className="mm-input w-28"
                  value={yearMaxStr}
                  disabled={busy}
                  onChange={(e) => setYearMaxStr(e.target.value)}
                />
              </label>
            </div>
          ) : (
            <p className="text-xs text-[var(--mm-text2)]">
              {scopeRow?.preview_year_min ?? "—"} to {scopeRow?.preview_year_max ?? "—"}
            </p>
          )}
        </div>
        <div className="space-y-2" data-testid="pruner-studio-preview-panel">
          <p className="text-sm font-medium text-[var(--mm-text1)]">Studio filter</p>
          <p className="text-xs text-[var(--mm-text3)]">Comma-separated studio names.</p>
          {showInteractiveControls ? (
            <input
              type="text"
              className="mm-input w-full"
              placeholder="e.g. Warner Bros., BBC"
              value={studioText}
              disabled={busy}
              onChange={(e) => setStudioText(e.target.value)}
            />
          ) : (
            <p className="text-xs text-[var(--mm-text2)]">
              {(scopeRow?.preview_include_studios ?? []).join(", ") || "none"}
            </p>
          )}
        </div>
        {isPlex && props.scope === "movies" ? (
          <div className="space-y-2" data-testid="pruner-collection-preview-panel">
            <p className="text-sm font-medium text-[var(--mm-text1)]">Collection filter (Plex)</p>
            <p className="text-xs text-[var(--mm-text3)]">Comma-separated collection names.</p>
            {showInteractiveControls ? (
              <input
                type="text"
                className="mm-input w-full"
                placeholder="e.g. Marvel Cinematic Universe"
                value={collectionText}
                disabled={busy}
                onChange={(e) => setCollectionText(e.target.value)}
              />
            ) : (
              <p className="text-xs text-[var(--mm-text2)]">
                {(scopeRow?.preview_include_collections ?? []).join(", ") || "none"}
              </p>
            )}
          </div>
        ) : null}
      </div>
    );
  }

  function renderProviderScheduleControls(): ReactNode {
    return (
      <div className="space-y-6">
        <p className="text-xs leading-relaxed text-[var(--mm-text3)]">
          Preview saves a snapshot. Apply uses the selected snapshot only.
        </p>
        <div className="space-y-2" data-testid="pruner-run-limits-panel">
          <p className="text-sm font-medium text-[var(--mm-text1)]">Preview cap per run</p>
          <p className="text-xs text-[var(--mm-text3)]">Between 1 and 5000 items.</p>
          {showInteractiveControls ? (
            <input
              type="number"
              min={1}
              max={5000}
              className="mm-input w-32"
              value={previewMaxItems}
              disabled={busy}
              onChange={(e) => setPreviewMaxItems(Math.max(1, Math.min(5000, Number(e.target.value) || 500)))}
            />
          ) : (
            <p className="text-xs text-[var(--mm-text2)]">{scopeRow?.preview_max_items ?? "—"}</p>
          )}
        </div>
        <div className="space-y-3" data-testid="pruner-scope-scheduled-preview">
          <p className="text-sm font-medium text-[var(--mm-text1)]">Scheduled previews</p>
          <p className="text-xs text-[var(--mm-text3)]">
            Interval 60 seconds to 24 hours. Scheduled runs use the missing primary art rule only.
          </p>
          {showInteractiveControls ? (
            <>
              <label className="flex items-center gap-2 text-sm text-[var(--mm-text)]">
                <input
                  type="checkbox"
                  checked={schedEnabled}
                  disabled={busy}
                  onChange={(e) => setSchedEnabled(e.target.checked)}
                />
                Enable scheduled previews
              </label>
              <label className="block text-sm text-[var(--mm-text2)]">
                <span className="mb-1 block text-xs text-[var(--mm-text3)]">Interval (seconds)</span>
                <input
                  type="number"
                  min={60}
                  max={86400}
                  className="mm-input w-36"
                  value={schedInterval}
                  disabled={busy}
                  onChange={(e) => setSchedInterval(parseInt(e.target.value, 10) || 3600)}
                />
              </label>
            </>
          ) : (
            <p className="text-xs text-[var(--mm-text2)]">
              Scheduled preview is <strong>{scopeRow?.scheduled_preview_enabled ? "on" : "off"}</strong>
              {scopeRow ? <> (every {scopeRow.scheduled_preview_interval_seconds}s).</> : null}
            </p>
          )}
          <p className="text-xs text-[var(--mm-text3)]">
            Last scheduled enqueue:{" "}
            <span className="text-[var(--mm-text2)]">
              {scopeRow?.last_scheduled_preview_enqueued_at
                ? new Date(scopeRow.last_scheduled_preview_enqueued_at).toLocaleString()
                : "—"}
            </span>
          </p>
        </div>
        {showInteractiveControls ? (
          <div className="space-y-4 border-t border-[var(--mm-border)] pt-4">
            <p className="text-sm font-medium text-[var(--mm-text1)]">On-demand previews</p>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className={fetcherMenuButtonClass({ variant: "secondary", disabled: busy })}
                disabled={busy}
                onClick={() => void runPreview()}
              >
                Queue missing-primary preview
              </button>
              <button
                type="button"
                className={fetcherMenuButtonClass({ variant: "secondary", disabled: busy || !scopeRow?.last_preview_run_uuid })}
                disabled={busy || !scopeRow?.last_preview_run_uuid}
                onClick={() => void loadJsonFor(scopeRow?.last_preview_run_uuid)}
              >
                Load latest snapshot JSON
              </button>
              {scopeRow?.last_preview_run_uuid ? (
                <button
                  type="button"
                  className={fetcherMenuButtonClass({ variant: "secondary", disabled: busy })}
                  disabled={busy}
                  onClick={() => openApplyModal(scopeRow.last_preview_run_uuid!)}
                >
                  Apply latest snapshot
                </button>
              ) : null}
            </div>
            <div className="flex flex-wrap gap-2">
              {props.scope === "tv" && !isPlex ? (
                <>
                  <button
                    type="button"
                    className={fetcherMenuButtonClass({ variant: "tertiary", disabled: busy || !staleNeverEnabled })}
                    disabled={busy || !staleNeverEnabled}
                    onClick={() => void runStaleNeverPreview()}
                  >
                    Preview never-played TV
                  </button>
                  <button
                    type="button"
                    className={fetcherMenuButtonClass({ variant: "tertiary", disabled: busy || !watchedTvEnabled })}
                    disabled={busy || !watchedTvEnabled}
                    onClick={() => void runWatchedTvPreview()}
                  >
                    Preview watched TV
                  </button>
                </>
              ) : null}
              {props.scope === "movies" ? (
                <>
                  <button
                    type="button"
                    className={fetcherMenuButtonClass({ variant: "tertiary", disabled: busy || !watchedMoviesEnabled })}
                    disabled={busy || !watchedMoviesEnabled}
                    onClick={() => void runWatchedMoviesPreview()}
                  >
                    Preview watched movies
                  </button>
                  <button
                    type="button"
                    className={fetcherMenuButtonClass({ variant: "tertiary", disabled: busy || !lowRatingEnabled })}
                    disabled={busy || !lowRatingEnabled}
                    onClick={() => void runLowRatingMoviesPreview()}
                  >
                    Preview low-rating movies
                  </button>
                  <button
                    type="button"
                    className={fetcherMenuButtonClass({ variant: "tertiary", disabled: busy || !unwatchedStaleEnabled })}
                    disabled={busy || !unwatchedStaleEnabled}
                    onClick={() => void runUnwatchedStaleMoviesPreview()}
                  >
                    Preview unwatched stale movies
                  </button>
                </>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>
    );
  }

  if (isProvider && provSub === "rules") {
    const saveLabel = props.scope === "tv" ? "Save TV rules" : "Save Movies rules";
    const onSave = props.scope === "tv" ? saveProviderTvRulesBundle : saveProviderMoviesRulesBundle;
    const saveDisabled = busy || !showInteractiveControls || (isPlex && props.scope === "tv");
    return (
      <section className="flex min-h-0 w-full min-w-0 flex-1 flex-col" data-testid={`pruner-provider-subsection-rules-${props.scope}`}>
        <fieldset disabled={Boolean(props.disabledMode)} className="flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 space-y-6">{renderProviderRulesControls()}</div>
          {showInteractiveControls ? (
            <div className="mt-8 border-t border-[var(--mm-border)] pt-5">
              <button
                type="button"
                className={fetcherMenuButtonClass({ variant: "primary", disabled: saveDisabled })}
                disabled={saveDisabled}
                onClick={() => void onSave()}
              >
                {busy ? "Saving…" : saveLabel}
              </button>
            </div>
          ) : null}
          {bundleMsg ? <p className="mt-3 text-sm text-green-600">{bundleMsg}</p> : null}
          {err ? (
            <p className="mt-2 text-sm text-red-600" role="alert">
              {err}
            </p>
          ) : null}
        </fieldset>
      </section>
    );
  }

  if (isProvider && provSub === "filters") {
    const saveLabel = props.scope === "tv" ? "Save TV filters" : "Save Movies filters";
    return (
      <section className="flex min-h-0 w-full min-w-0 flex-1 flex-col" data-testid={`pruner-provider-subsection-filters-${props.scope}`}>
        <fieldset disabled={Boolean(props.disabledMode)} className="flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 space-y-6">{renderProviderFiltersControls()}</div>
          {showInteractiveControls ? (
            <div className="mt-8 border-t border-[var(--mm-border)] pt-5">
              <button
                type="button"
                className={fetcherMenuButtonClass({ variant: "primary", disabled: busy })}
                disabled={busy}
                onClick={() => void saveProviderFiltersBundle()}
              >
                {busy ? "Saving…" : saveLabel}
              </button>
            </div>
          ) : null}
          {bundleMsg ? <p className="mt-3 text-sm text-green-600">{bundleMsg}</p> : null}
          {err ? (
            <p className="mt-2 text-sm text-red-600" role="alert">
              {err}
            </p>
          ) : null}
        </fieldset>
      </section>
    );
  }

  if (isProvider && provSub === "schedule") {
    const saveLabel = props.scope === "tv" ? "Save TV schedule" : "Save Movies schedule";
    return (
      <section className="flex min-h-0 w-full min-w-0 flex-1 flex-col" data-testid={`pruner-provider-subsection-schedule-${props.scope}`}>
        <fieldset disabled={Boolean(props.disabledMode)} className="flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 space-y-6">{renderProviderScheduleControls()}</div>
          {showInteractiveControls ? (
            <div className="mt-8 border-t border-[var(--mm-border)] pt-5">
              <button
                type="button"
                className={fetcherMenuButtonClass({ variant: "primary", disabled: busy })}
                disabled={busy}
                onClick={() => void saveProviderScheduleBundle()}
              >
                {busy ? "Saving…" : saveLabel}
              </button>
            </div>
          ) : null}
          {bundleMsg ? <p className="mt-3 text-sm text-green-600">{bundleMsg}</p> : null}
          {schedMsg ? <p className="mt-1 text-xs text-green-600">{schedMsg}</p> : null}
          {previewMaxItemsMsg ? <p className="mt-1 text-xs text-green-600">{previewMaxItemsMsg}</p> : null}
          {err ? (
            <p className="mt-2 text-sm text-red-600" role="alert">
              {err}
            </p>
          ) : null}
          {preview ? <p className="mt-2 text-sm text-[var(--mm-text)]">{preview}</p> : null}
          {jsonPreview ? (
            <pre className="mt-3 max-h-96 overflow-auto rounded-md border border-[var(--mm-border)] bg-[var(--mm-surface2)] p-3 text-xs">
              {jsonPreview}
            </pre>
          ) : null}
        </fieldset>
        {applyModalRunId ? (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
            role="dialog"
            aria-modal="true"
            aria-labelledby="pruner-apply-modal-title-2"
            data-testid="pruner-apply-modal"
          >
            <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-4 shadow-xl">
              <h3 id="pruner-apply-modal-title-2" className="text-base font-semibold text-[var(--mm-text)]">
                {applySnapshotOperatorLabel ?? "Apply from preview snapshot"}
              </h3>
              <p className="mt-2 text-sm text-[var(--mm-text2)]">
                This live action uses <strong>only</strong> the frozen candidate list from one preview snapshot.
              </p>
              {applyEligQuery.isLoading ? (
                <p className="mt-3 text-sm text-[var(--mm-text2)]">Checking eligibility…</p>
              ) : applyEligQuery.isError ? (
                <p className="mt-3 text-sm text-red-600" role="alert">
                  {(applyEligQuery.error as Error).message}
                </p>
              ) : applyEligQuery.data ? (
                <ul className="mt-3 list-inside list-disc space-y-1 text-sm text-[var(--mm-text)]">
                  <li>
                    Scope: <strong>{applyEligQuery.data.media_scope === "tv" ? "TV" : "Movies"}</strong>
                  </li>
                  <li>
                    Candidates: <strong>{applyEligQuery.data.candidate_count}</strong>
                  </li>
                </ul>
              ) : null}
              {applyEligQuery.data && !applyEligQuery.data.eligible ? (
                <p className="mt-3 text-sm text-amber-700" role="status">
                  {applyEligQuery.data.reasons.length
                    ? applyEligQuery.data.reasons.join(" ")
                    : "This snapshot cannot be applied right now."}
                </p>
              ) : null}
              {applyEligQuery.data?.eligible ? (
                <label className="mt-4 flex cursor-pointer items-start gap-2 text-sm text-[var(--mm-text)]">
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={applySnapshotConfirmed}
                    onChange={(e) => setApplySnapshotConfirmed(e.target.checked)}
                  />
                  <span>I confirm this apply for the selected snapshot only.</span>
                </label>
              ) : null}
              <div className="mt-4 flex flex-wrap justify-end gap-2">
                <button
                  type="button"
                  className="rounded-md border border-[var(--mm-border)] px-3 py-1.5 text-sm font-medium text-[var(--mm-text)]"
                  onClick={() => closeApplyModal()}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="rounded-md bg-red-800 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                  data-testid="pruner-apply-confirm"
                  disabled={
                    busy ||
                    !applyEligQuery.data?.eligible ||
                    !applySnapshotConfirmed ||
                    applyEligQuery.isLoading ||
                    applyEligQuery.isError
                  }
                  onClick={() => void confirmApplyFromSnapshot()}
                >
                  {applySnapshotOperatorLabel ?? "Confirm apply"}
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </section>
    );
  }

  if (isProvider && !provSub) {
    return (
      <p className="text-sm text-red-600" role="alert" data-testid="pruner-provider-subsection-missing">
        Provider configuration is missing an internal subsection id.
      </p>
    );
  }

  return (
    <section
      className={isProvider ? "w-full min-w-0 space-y-3" : "max-w-3xl space-y-3"}
      aria-labelledby="pruner-scope-heading"
    >
      <fieldset disabled={Boolean(props.disabledMode)} className="space-y-3">
      {!isProvider ? (
        <h2 id="pruner-scope-heading" className="text-base font-semibold text-[var(--mm-text)]">
          {label}
        </h2>
      ) : (
        <h2 id="pruner-scope-heading" className="sr-only">
          {label}
        </h2>
      )}
      {props.disabledMode && !isProvider ? (
        <p className="rounded-md border border-dashed border-[var(--mm-border)] bg-[var(--mm-surface2)]/35 px-3 py-2 text-xs text-[var(--mm-text2)]">
          Save this provider connection first to activate these controls.
        </p>
      ) : null}
      <div
        className="space-y-2 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
        data-testid="pruner-run-limits-panel"
      >
        <p className="text-sm font-semibold text-[var(--mm-text)]">Run limits</p>
        <p className="text-xs text-[var(--mm-text2)]" data-testid="pruner-delete-cap-note">
          Preview cap is configurable. Per-scope apply/delete cap is not exposed in the Pruner API — apply uses the frozen
          snapshot only.
        </p>
        {showInteractiveControls ? (
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-xs text-[var(--mm-text2)]">
              Preview cap per run (1–5000)
              <input
                type="number"
                min={1}
                max={5000}
                value={previewMaxItems}
                disabled={busy}
                onChange={(e) => setPreviewMaxItems(Math.max(1, Math.min(5000, Number(e.target.value) || 500)))}
                className="ml-2 w-24 rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-1 text-sm text-[var(--mm-text)]"
              />
            </label>
            <button
              type="button"
              className="rounded-md border border-[var(--mm-border)] px-3 py-1 text-sm font-medium text-[var(--mm-text)] disabled:opacity-50"
              disabled={busy}
              onClick={() => void savePreviewMaxItemsSettings()}
            >
              Save run limits
            </button>
            {previewMaxItemsMsg ? <p className="text-xs text-green-600">{previewMaxItemsMsg}</p> : null}
          </div>
        ) : (
          <p className="text-xs text-[var(--mm-text2)]">
            Preview cap: <strong>{scopeRow?.preview_max_items ?? "—"}</strong>. Sign in as an operator to edit.
          </p>
        )}
      </div>
      <div
        className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-surface2)]/40 px-4 py-3 text-xs text-[var(--mm-text2)] sm:text-sm"
        data-testid="pruner-scope-trust-banner"
      >
        <p>
          Preview saves a snapshot. Apply uses the selected snapshot only.
        </p>
      </div>
      {!isProvider && !isPlex ? (
        <p className="text-sm text-[var(--mm-text2)]">
          {props.scope === "tv"
            ? "Previews list episodes missing a primary image (episode-level rows only), or episodes that are unplayed for the MediaMop token and older than your age threshold by library DateCreated — each rule has its own preview queue."
            : "Previews list movie items missing a primary image (one row per movie), movies the server marks watched for the MediaMop token, or movies that are unplayed and older than your age threshold by library DateCreated — each rule has its own preview queue."}
        </p>
      ) : !isProvider ? (
        <p className="text-sm text-[var(--mm-text2)]">
          For <strong>Remove broken library entries</strong>, Plex uses the same{" "}
          <strong>preview → inspect JSON → apply</strong> flow as Jellyfin and Emby on this tab. Missing-primary preview
          lists movie or episode leaves where the item JSON has an empty or missing <code className="text-[0.85em]">thumb</code>{" "}
          — that is <strong>not</strong> the same signal as Jellyfin/Emby primary-image probes. On the{" "}
          <strong>Movies</strong> tab, Plex also supports watched movies, watched low-rating movies (leaf{" "}
          <code className="text-[0.85em]">audienceRating</code>), and unwatched stale movies (leaf{" "}
          <code className="text-[0.85em]">addedAt</code> age), all via the same <code className="text-[0.85em]">allLeaves</code>{" "}
          read with your token — no separate account API. Apply only touches the frozen{" "}
          <code className="text-[0.85em]">ratingKey</code> values from the snapshot; if an entry is already gone, the job
          counts it as skipped. MediaMop does not claim whether Plex removes only metadata or also media files — that
          depends on your Plex server.
        </p>
      ) : null}
      {isProvider ? (
        <p className="text-xs text-[var(--mm-text2)]">
          Queue preview, inspect JSON, then apply from the latest snapshot.
        </p>
      ) : null}
      {isPlex && scopeRow && !isProvider ? (
        <p className="text-xs text-[var(--mm-text2)]" data-testid="pruner-plex-preview-cap-note">
          Missing-primary Plex previews collect at most{" "}
          <strong>
            min(per-tab item cap {scopeRow.preview_max_items}, MEDIAMOP_PRUNER_PLEX_LIVE_ABS_MAX_ITEMS)
          </strong>{" "}
          matching leaves per run (also clamped to 5000 like other preview kinds). Successful preview activity includes{" "}
          <code className="text-[0.85em]">plex_missing_primary_item_cap</code> and a short cap note. When a run shows
          &quot;truncated&quot;, Plex had more matches than that cap — the snapshot is never silently widened.
        </p>
      ) : null}
      {isPlex && props.scope === "tv" && isProvider ? (
        <div className="space-y-2" data-testid="pruner-provider-plex-tv-unsupported-rules">
          <div
            className="space-y-2 rounded-md border border-amber-600/40 bg-amber-950/20 px-4 py-3 text-sm text-[var(--mm-text)]"
            data-testid="pruner-plex-tv-watched-unsupported"
          >
            <p className="text-sm font-semibold text-amber-100">Watched TV removal</p>
            <label className="flex cursor-not-allowed items-center gap-2 text-sm text-[var(--mm-text2)]">
              <input type="checkbox" disabled checked={false} readOnly className="opacity-60" />
              Not supported for Plex.
            </label>
          </div>
          <div
            className="space-y-2 rounded-md border border-amber-600/40 bg-amber-950/20 px-4 py-3 text-sm text-[var(--mm-text)]"
            data-testid="pruner-plex-tv-never-played-unsupported"
          >
            <p className="text-sm font-semibold text-amber-100">Never-played TV older than N days</p>
            <label className="flex cursor-not-allowed items-center gap-2 text-sm text-[var(--mm-text2)]">
              <input type="checkbox" disabled checked={false} readOnly className="opacity-60" />
              Not supported for Plex.
            </label>
            <label className="block text-xs text-[var(--mm-text2)]">
              Minimum age (days)
              <input
                type="number"
                disabled
                readOnly
                className="ml-2 mt-1 w-24 cursor-not-allowed rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-1 text-sm opacity-60"
                value={90}
              />
            </label>
          </div>
        </div>
      ) : null}
      <div>
        <h3 className="text-base font-semibold text-[var(--mm-text)]" data-testid="pruner-filters-section-heading">
          Preview narrowing filters
        </h3>
        <p className="text-xs text-[var(--mm-text2)]">
          Filters affect preview collection in this {sectionWord} only.
        </p>
        {isPlex && props.scope === "tv" && isProvider ? (
          <p className="mt-1 text-xs text-amber-100/90" data-testid="pruner-plex-tv-filters-scope-note" role="status">
            On Plex TV, genre, people, year, and studio filters apply to the <strong>missing primary art</strong> preview
            rule only.
          </p>
        ) : null}
      </div>
      {scopeRow ? (
        <div
          className="space-y-2 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
          data-testid="pruner-genre-filters-panel"
        >
          <p className="text-sm font-semibold text-[var(--mm-text)]">
            Optional preview genre include (this {sectionWord} only)
          </p>
          <p className="text-xs text-[var(--mm-text2)]">Comma-separated genres.</p>
          {isPlex && !isProvider ? (
            <p
              className="text-xs text-amber-100/90"
              data-testid="pruner-plex-genre-empty-preview-note"
            >
              If a preview finishes successfully with <strong>zero rows</strong> while filters are set, that usually
              means nothing in this pass matched the rule under those genres — not that Plex reports nothing to clean.
              Matching uses Genre tags on each <code className="text-[0.85em]">allLeaves</code> leaf only.
            </p>
          ) : null}
          {showInteractiveControls ? (
            <div className="space-y-2">
              <input
                type="text"
                className="w-full rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-1 text-sm text-[var(--mm-text)]"
                placeholder="e.g. Drama, Science Fiction"
                value={genreText}
                disabled={busy}
                onChange={(e) => setGenreText(e.target.value)}
              />
              <button
                type="button"
                className="rounded-md border border-[var(--mm-border)] px-3 py-1 text-sm font-medium text-[var(--mm-text)] disabled:opacity-50"
                disabled={busy}
                onClick={() => void saveGenreFilters()}
              >
                Save genre filters
              </button>
              {genreMsg ? <p className="text-xs text-green-600">{genreMsg}</p> : null}
            </div>
          ) : (
            <p className="text-xs text-[var(--mm-text2)]">
              Current filters:{" "}
              <strong>{(scopeRow.preview_include_genres ?? []).length ? scopeRow.preview_include_genres.join(", ") : "none"}</strong>
              . Sign in as an operator to edit.
            </p>
          )}
        </div>
      ) : null}
      {scopeRow ? (
        <div
          className="space-y-2 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
          data-testid="pruner-people-filters-panel"
        >
          <p className="text-sm font-semibold text-[var(--mm-text)]">
            Optional preview people include (this {sectionWord} only)
          </p>
          <p className="text-xs text-[var(--mm-text2)]">Comma-separated full names.</p>
          {isPlex && props.scope === "tv" && isProvider ? null : isPlex && !isProvider ? (
            <p className="text-xs text-[var(--mm-text2)]" data-testid="pruner-people-plex-note">
              Plex: applies to previews that read <code className="text-[0.85em]">allLeaves</code> on this scope (missing
              primary art, watched movies, low-rating, unwatched stale). Names come from <strong>Role</strong>,{" "}
              <strong>Writer</strong>, and <strong>Director</strong> tag strings on each leaf (no separate metadata fetch).
            </p>
          ) : !isProvider ? (
            <p className="text-xs text-[var(--mm-text2)]" data-testid="pruner-people-jf-emby-note">
              Jellyfin / Emby: uses each item&apos;s <strong>People</strong> list from the Items API when filters are
              saved (MediaMop requests explicit Fields). Applies to every preview rule on this scope.
            </p>
          ) : null}
          {showInteractiveControls ? (
            <div className="space-y-2">
              <input
                type="text"
                className="w-full rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-1 text-sm text-[var(--mm-text)]"
                placeholder="e.g. Jane Doe, Alan Smithee"
                value={peopleText}
                disabled={busy}
                onChange={(e) => setPeopleText(e.target.value)}
              />
              <button
                type="button"
                className="rounded-md border border-[var(--mm-border)] px-3 py-1 text-sm font-medium text-[var(--mm-text)] disabled:opacity-50"
                disabled={busy}
                onClick={() => void savePeopleFilters()}
              >
                Save people filters
              </button>
              {peopleMsg ? <p className="text-xs text-green-600">{peopleMsg}</p> : null}
            </div>
          ) : (
            <p className="text-xs text-[var(--mm-text2)]">
              Current people filters:{" "}
              <strong>
                {(scopeRow.preview_include_people ?? []).length
                  ? scopeRow.preview_include_people.join(", ")
                  : "none"}
              </strong>
              . Sign in as an operator to edit.
            </p>
          )}
        </div>
      ) : null}
      {scopeRow ? (
        <div
          className="space-y-2 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
          data-testid="pruner-year-filters-panel"
        >
          <p className="text-sm font-semibold text-[var(--mm-text)]">Optional preview year range (this {sectionWord} only)</p>
          <p className="text-xs text-[var(--mm-text2)]">Inclusive 1900-2100. Blank means open-ended.</p>
          {showInteractiveControls ? (
            <div className="flex flex-wrap items-end gap-2">
              <label className="text-xs text-[var(--mm-text2)]">
                Min year
                <input
                  type="number"
                  min={1900}
                  max={2100}
                  className="ml-1 w-24 rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-1 text-sm text-[var(--mm-text)]"
                  value={yearMinStr}
                  disabled={busy}
                  onChange={(e) => setYearMinStr(e.target.value)}
                />
              </label>
              <label className="text-xs text-[var(--mm-text2)]">
                Max year
                <input
                  type="number"
                  min={1900}
                  max={2100}
                  className="ml-1 w-24 rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-1 text-sm text-[var(--mm-text)]"
                  value={yearMaxStr}
                  disabled={busy}
                  onChange={(e) => setYearMaxStr(e.target.value)}
                />
              </label>
              <button
                type="button"
                className="rounded-md border border-[var(--mm-border)] px-3 py-1 text-sm font-medium text-[var(--mm-text)] disabled:opacity-50"
                disabled={busy}
                onClick={() => void savePreviewYearBounds()}
              >
                Save year bounds
              </button>
              {yearMsg ? <p className="w-full text-xs text-green-600">{yearMsg}</p> : null}
            </div>
          ) : (
            <p className="text-xs text-[var(--mm-text2)]">
              Current bounds:{" "}
              <strong>
                {scopeRow.preview_year_min ?? "—"} to {scopeRow.preview_year_max ?? "—"}
              </strong>
              . Sign in as an operator to edit.
            </p>
          )}
        </div>
      ) : null}
      {scopeRow ? (
        <div
          className="space-y-2 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
          data-testid="pruner-studio-preview-panel"
        >
          <p className="text-sm font-semibold text-[var(--mm-text)]">Optional preview studio include (this {sectionWord} only)</p>
          <p className="text-xs text-[var(--mm-text2)]">Comma-separated studio names.</p>
          {showInteractiveControls ? (
            <div className="space-y-2">
              <input
                type="text"
                className="w-full rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-1 text-sm text-[var(--mm-text)]"
                placeholder="e.g. Warner Bros., BBC"
                value={studioText}
                disabled={busy}
                onChange={(e) => setStudioText(e.target.value)}
              />
              <button
                type="button"
                className="rounded-md border border-[var(--mm-border)] px-3 py-1 text-sm font-medium text-[var(--mm-text)] disabled:opacity-50"
                disabled={busy}
                onClick={() => void saveStudioPreviewFilters()}
              >
                Save studio filters
              </button>
              {studioMsg ? <p className="text-xs text-green-600">{studioMsg}</p> : null}
            </div>
          ) : (
            <p className="text-xs text-[var(--mm-text2)]">
              Current studio filters:{" "}
              <strong>
                {(scopeRow.preview_include_studios ?? []).length
                  ? scopeRow.preview_include_studios.join(", ")
                  : "none"}
              </strong>
              .
            </p>
          )}
        </div>
      ) : null}
      {scopeRow && isPlex ? (
        <div
          className="space-y-2 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
          data-testid="pruner-collection-preview-panel"
        >
          <p className="text-sm font-semibold text-[var(--mm-text)]">
            Optional preview collection include (Plex allLeaves movie previews)
          </p>
          <p className="text-xs text-[var(--mm-text2)]">Comma-separated collection names.</p>
          {showInteractiveControls ? (
            <div className="space-y-2">
              <input
                type="text"
                className="w-full rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-1 text-sm text-[var(--mm-text)]"
                placeholder="e.g. Marvel Cinematic Universe"
                value={collectionText}
                disabled={busy}
                onChange={(e) => setCollectionText(e.target.value)}
              />
              <button
                type="button"
                className="rounded-md border border-[var(--mm-border)] px-3 py-1 text-sm font-medium text-[var(--mm-text)] disabled:opacity-50"
                disabled={busy}
                onClick={() => void saveCollectionPreviewFilters()}
              >
                Save collection filters
              </button>
              {collectionMsg ? <p className="text-xs text-green-600">{collectionMsg}</p> : null}
            </div>
          ) : (
            <p className="text-xs text-[var(--mm-text2)]">
              Current collection filters:{" "}
              <strong>
                {(scopeRow.preview_include_collections ?? []).length
                  ? scopeRow.preview_include_collections.join(", ")
                  : "none"}
              </strong>
              .
            </p>
          )}
        </div>
      ) : null}
      {isPlex ? (
        <div
          className="rounded-md border border-amber-600/40 bg-amber-950/20 px-3 py-2 text-xs text-[var(--mm-text)]"
          role="status"
          data-testid="pruner-plex-other-rules-note"
        >
          <p className="font-medium text-amber-100">
            {props.scope === "movies"
              ? "Plex: watched TV and never-played stale are unsupported."
              : "Plex: watched TV and never-played stale are unsupported in this scope."}
          </p>
        </div>
      ) : null}
      {!isPlex ? (
        <Fragment>
        <div
          className="space-y-2 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
          data-testid="pruner-never-played-stale-panel"
        >
          <p className="text-sm font-semibold text-[var(--mm-text)]">
            {props.scope === "tv"
              ? "Never-played TV older than N days (Jellyfin / Emby)"
              : "Never-played entries older than N days (Jellyfin / Emby)"}
          </p>
          <p className="text-xs text-[var(--mm-text2)]">Never played and older than this age.</p>
          {showInteractiveControls ? (
            <div className="space-y-2">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={staleNeverEnabled}
                  disabled={busy}
                  onChange={(e) => setStaleNeverEnabled(e.target.checked)}
                />
                {props.scope === "tv"
                  ? "Enable never-played TV older-than rule for this scope"
                  : "Enable never-played older-than rule for this scope"}
              </label>
              <div className="flex flex-wrap items-center gap-2">
                <label className="text-sm text-[var(--mm-text2)]">
                  Minimum age (days, 7–3650):{" "}
                  <input
                    type="number"
                    min={7}
                    max={3650}
                    className="w-24 rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-1 text-sm text-[var(--mm-text)]"
                    value={staleNeverDays}
                    disabled={busy}
                    onChange={(e) => setStaleNeverDays(parseInt(e.target.value, 10) || 90)}
                  />
                </label>
                <button
                  type="button"
                  className="rounded-md border border-[var(--mm-border)] px-3 py-1 text-sm font-medium text-[var(--mm-text)] disabled:opacity-50"
                  disabled={busy}
                  onClick={() => void saveStaleNeverSettings()}
                >
                  Save never-played rule
                </button>
              </div>
              {staleNeverMsg ? <p className="text-xs text-green-600">{staleNeverMsg}</p> : null}
              <button
                type="button"
                className="rounded-md bg-[var(--mm-surface2)] px-3 py-1.5 text-sm font-medium text-[var(--mm-text)] ring-1 ring-[var(--mm-border)] disabled:opacity-50"
                disabled={busy || !staleNeverEnabled}
                title={!staleNeverEnabled ? "Enable the rule and save before queueing a preview for it." : undefined}
                onClick={() => void runStaleNeverPreview()}
              >
                {props.scope === "tv"
                  ? "Queue preview (never-played TV older than N days)"
                  : "Queue preview (never-played older than N days)"}
              </button>
            </div>
          ) : (
            <p className="text-xs text-[var(--mm-text2)]">
              Rule is <strong>{scopeRow?.never_played_stale_reported_enabled ? "on" : "off"}</strong>
              {scopeRow ? (
                <>
                  {" "}
                  (minimum age {scopeRow.never_played_min_age_days} days). Sign in as an operator to change it.
                </>
              ) : null}
            </p>
          )}
        </div>
        {props.scope === "tv" ? (
          <div
            className="space-y-2 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
            data-testid="pruner-watched-tv-panel"
          >
            <p className="text-sm font-semibold text-[var(--mm-text)]">
              Watched TV (Jellyfin / Emby, TV scope only)
            </p>
            <p className="text-xs text-[var(--mm-text2)]">Delete items marked watched for this provider user.</p>
            {showInteractiveControls ? (
              <div className="space-y-2">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={watchedTvEnabled}
                    disabled={busy}
                    onChange={(e) => setWatchedTvEnabled(e.target.checked)}
                  />
                  Enable watched TV rule for this TV scope
                </label>
                <button
                  type="button"
                  className="rounded-md border border-[var(--mm-border)] px-3 py-1 text-sm font-medium text-[var(--mm-text)] disabled:opacity-50"
                  disabled={busy}
                  onClick={() => void saveWatchedTvSettings()}
                >
                  Save watched TV rule
                </button>
                {watchedTvMsg ? <p className="text-xs text-green-600">{watchedTvMsg}</p> : null}
                <button
                  type="button"
                  className="rounded-md bg-[var(--mm-surface2)] px-3 py-1.5 text-sm font-medium text-[var(--mm-text)] ring-1 ring-[var(--mm-border)] disabled:opacity-50"
                  disabled={busy || !watchedTvEnabled}
                  title={!watchedTvEnabled ? "Enable the rule and save before queueing a preview for it." : undefined}
                  onClick={() => void runWatchedTvPreview()}
                >
                  Queue preview (watched TV)
                </button>
              </div>
            ) : (
              <p className="text-xs text-[var(--mm-text2)]">
                Watched TV rule is <strong>{scopeRow?.watched_tv_reported_enabled ? "on" : "off"}</strong> for this{" "}
                {sectionWord}.
                Sign in as an operator to change it.
              </p>
            )}
          </div>
        ) : null}
        </Fragment>
      ) : null}
      {!isPlex ? null : props.scope === "movies" && !isProvider ? (
        <p className="text-xs text-[var(--mm-text2)]">
          Watched / low-rating / unwatched stale movie previews on Plex use the same{" "}
          <code className="text-[0.85em]">allLeaves</code> token-scoped metadata as other Plex previews: watched means{" "}
          <code className="text-[0.85em]">viewCount</code> ≥ 1 or a positive <code className="text-[0.85em]">lastViewedAt</code>
          ; low-rating compares your saved Plex audienceRating ceiling to leaf <code className="text-[0.85em]">audienceRating</code>{" "}
          (not Jellyfin/Emby <code className="text-[0.85em]">CommunityRating</code>); stale unwatched uses library{" "}
          <code className="text-[0.85em]">addedAt</code> age, not <code className="text-[0.85em]">DateCreated</code>.
        </p>
      ) : null}
      <div>
        <h3 className="text-base font-semibold text-[var(--mm-text)]" data-testid="pruner-rules-section-heading">
          Cleanup rules
        </h3>
        <p className="text-xs text-[var(--mm-text2)]">Enable, save, then queue preview.</p>
      </div>
      {props.scope === "movies" ? (
          <>
            <div
              className="space-y-2 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
              data-testid="pruner-watched-movies-panel"
            >
              <p className="text-sm font-semibold text-[var(--mm-text)]">
                {isPlex
                  ? "Watched movies (Plex, Movies scope only)"
                  : "Watched movies (Jellyfin / Emby, Movies scope only)"}
              </p>
              <p className="text-xs text-[var(--mm-text2)]">
                {isPlex ? "Uses Plex watched state from allLeaves." : "Uses provider watched state for movie items."}
              </p>
              {showInteractiveControls ? (
                <div className="space-y-2">
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={watchedMoviesEnabled}
                      disabled={busy}
                      onChange={(e) => setWatchedMoviesEnabled(e.target.checked)}
                    />
                    Enable watched movies rule for this Movies scope
                  </label>
                  <button
                    type="button"
                    className="rounded-md border border-[var(--mm-border)] px-3 py-1 text-sm font-medium text-[var(--mm-text)] disabled:opacity-50"
                    disabled={busy}
                    onClick={() => void saveWatchedMoviesSettings()}
                  >
                    Save watched movies rule
                  </button>
                  {watchedMoviesMsg ? <p className="text-xs text-green-600">{watchedMoviesMsg}</p> : null}
                  <button
                    type="button"
                    className="rounded-md bg-[var(--mm-surface2)] px-3 py-1.5 text-sm font-medium text-[var(--mm-text)] ring-1 ring-[var(--mm-border)] disabled:opacity-50"
                    disabled={busy || !watchedMoviesEnabled}
                    title={
                      !watchedMoviesEnabled ? "Enable the rule and save before queueing a preview for it." : undefined
                    }
                    onClick={() => void runWatchedMoviesPreview()}
                  >
                    Queue preview (watched movies)
                  </button>
                </div>
              ) : (
                <p className="text-xs text-[var(--mm-text2)]">
                  Watched movies rule is <strong>{scopeRow?.watched_movies_reported_enabled ? "on" : "off"}</strong> for
                  this tab. Sign in as an operator to change it.
                </p>
              )}
            </div>
            <div
              className="space-y-2 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
              data-testid="pruner-watched-low-rating-panel"
            >
              <p className="text-sm font-semibold text-[var(--mm-text)]">
                {isPlex
                  ? "Watched low-rating movies (Plex, Movies scope only)"
                  : "Watched low-rating movies (Jellyfin / Emby, Movies scope only)"}
              </p>
              <p className="text-xs text-[var(--mm-text2)]">
                {isPlex ? "Uses Plex audienceRating." : "Uses Jellyfin/Emby CommunityRating."}
              </p>
              {showInteractiveControls ? (
                <div className="space-y-2">
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={lowRatingEnabled}
                      disabled={busy}
                      onChange={(e) => setLowRatingEnabled(e.target.checked)}
                    />
                    Enable watched low-rating movies rule for this Movies scope
                  </label>
                  <label className="flex flex-wrap items-center gap-2 text-sm text-[var(--mm-text2)]">
                    {isPlex
                      ? "Plex audienceRating — max ceiling (0–10 inclusive)"
                      : "Jellyfin/Emby CommunityRating — max ceiling (0–10 inclusive)"}
                    <input
                      type="number"
                      min={0}
                      max={10}
                      step="0.1"
                      className="w-24 rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-1 text-sm text-[var(--mm-text)]"
                      value={lowRatingMax}
                      disabled={busy}
                      onChange={(e) => setLowRatingMax(e.target.value)}
                    />
                  </label>
                  <button
                    type="button"
                    className="rounded-md border border-[var(--mm-border)] px-3 py-1 text-sm font-medium text-[var(--mm-text)] disabled:opacity-50"
                    disabled={busy}
                    onClick={() => void saveLowRatingMovieSettings()}
                  >
                    Save low-rating rule
                  </button>
                  {lowRatingMsg ? <p className="text-xs text-green-600">{lowRatingMsg}</p> : null}
                  <button
                    type="button"
                    className="rounded-md bg-[var(--mm-surface2)] px-3 py-1.5 text-sm font-medium text-[var(--mm-text)] ring-1 ring-[var(--mm-border)] disabled:opacity-50"
                    disabled={busy || !lowRatingEnabled}
                    title={
                      !lowRatingEnabled ? "Enable the rule and save before queueing a preview for it." : undefined
                    }
                    onClick={() => void runLowRatingMoviesPreview()}
                  >
                    Queue preview (watched low-rating movies)
                  </button>
                </div>
              ) : (
                <p className="text-xs text-[var(--mm-text2)]">
                  Watched low-rating rule is{" "}
                  <strong>{scopeRow?.watched_movie_low_rating_reported_enabled ? "on" : "off"}</strong> (ceiling{" "}
                  {isPlex
                    ? `${scopeRow?.watched_movie_low_rating_max_plex_audience_rating} audienceRating`
                    : `${scopeRow?.watched_movie_low_rating_max_jellyfin_emby_community_rating} CommunityRating`}
                  ). Sign in as an operator to change it.
                </p>
              )}
            </div>
            <div
              className="space-y-2 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
              data-testid="pruner-unwatched-stale-panel"
            >
              <p className="text-sm font-semibold text-[var(--mm-text)]">
                {isPlex
                  ? "Unwatched stale movies (Plex, Movies scope only)"
                  : "Unwatched stale movies (Jellyfin / Emby, Movies scope only)"}
              </p>
              <p className="text-xs text-[var(--mm-text2)]">
                {isPlex ? "Unwatched + addedAt age." : "Never-played + DateCreated age."}
              </p>
              {showInteractiveControls ? (
                <div className="space-y-2">
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={unwatchedStaleEnabled}
                      disabled={busy}
                      onChange={(e) => setUnwatchedStaleEnabled(e.target.checked)}
                    />
                    Enable unwatched stale movies rule for this Movies scope
                  </label>
                  <label className="flex flex-wrap items-center gap-2 text-sm text-[var(--mm-text2)]">
                    Minimum age (days, 7–3650)
                    <input
                      type="number"
                      min={7}
                      max={3650}
                      className="w-24 rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-1 text-sm text-[var(--mm-text)]"
                      value={unwatchedStaleDays}
                      disabled={busy}
                      onChange={(e) => setUnwatchedStaleDays(parseInt(e.target.value, 10) || 90)}
                    />
                  </label>
                  <button
                    type="button"
                    className="rounded-md border border-[var(--mm-border)] px-3 py-1 text-sm font-medium text-[var(--mm-text)] disabled:opacity-50"
                    disabled={busy}
                    onClick={() => void saveUnwatchedStaleMovieSettings()}
                  >
                    Save unwatched stale rule
                  </button>
                  {unwatchedStaleMsg ? <p className="text-xs text-green-600">{unwatchedStaleMsg}</p> : null}
                  <button
                    type="button"
                    className="rounded-md bg-[var(--mm-surface2)] px-3 py-1.5 text-sm font-medium text-[var(--mm-text)] ring-1 ring-[var(--mm-border)] disabled:opacity-50"
                    disabled={busy || !unwatchedStaleEnabled}
                    title={
                      !unwatchedStaleEnabled ? "Enable the rule and save before queueing a preview for it." : undefined
                    }
                    onClick={() => void runUnwatchedStaleMoviesPreview()}
                  >
                    Queue preview (unwatched stale movies)
                  </button>
                </div>
              ) : (
                <p className="text-xs text-[var(--mm-text2)]">
                  Unwatched stale rule is <strong>{scopeRow?.unwatched_movie_stale_reported_enabled ? "on" : "off"}</strong>{" "}
                  (min age {scopeRow?.unwatched_movie_stale_min_age_days} days). Sign in as an operator to change it.
                </p>
              )}
            </div>
          </>
        ) : null}
      {!isProvider && scopeRow ? (
        <div
          className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text2)]"
          data-testid="pruner-scope-latest-preview-summary"
        >
          <h3 className="text-sm font-semibold text-[var(--mm-text)]">Latest preview job (this {sectionWord})</h3>
          <p className="mt-1 text-xs text-[var(--mm-text2)]">
            Denormalized from the last finished preview for quick orientation — see the history table for older runs.
          </p>
          <dl className="mt-2 space-y-1 text-xs sm:text-sm">
            <div>
              <dt className="inline text-[var(--mm-text3)]">When</dt>{" "}
              <dd className="inline font-medium text-[var(--mm-text1)]">
                {formatPrunerDateTime(scopeRow.last_preview_at)}
              </dd>
            </div>
            <div>
              <dt className="inline text-[var(--mm-text3)]">Outcome</dt>{" "}
              <dd className="inline font-medium text-[var(--mm-text1)]">{scopeRow.last_preview_outcome ?? "—"}</dd>
            </div>
            <div>
              <dt className="inline text-[var(--mm-text3)]">Candidates</dt>{" "}
              <dd className="inline font-medium text-[var(--mm-text1)]">{scopeRow.last_preview_candidate_count ?? "—"}</dd>
            </div>
            <div>
              <dt className="inline text-[var(--mm-text3)]">Error detail</dt>{" "}
              <dd className="inline text-[var(--mm-text1)]">{scopeRow.last_preview_error ?? "—"}</dd>
            </div>
          </dl>
        </div>
      ) : null}
      <div>
        <h3 className="text-base font-semibold text-[var(--mm-text)]" data-testid="pruner-actions-history-heading">
          {isProvider ? "Preview actions" : "Preview and apply actions"}
        </h3>
        {isProvider ? null : (
          <p className="text-xs text-[var(--mm-text2)]">
            Queue previews, inspect rows/JSON, then apply from one selected snapshot. The history table explains no
            candidates, filtered-out runs, and unsupported outcomes.
          </p>
        )}
      </div>
      {showInteractiveControls ? (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-md bg-[var(--mm-accent)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            disabled={busy}
            onClick={() => void runPreview()}
          >
            Queue preview (missing primary art)
          </button>
          <button
            type="button"
            className="rounded-md border border-[var(--mm-border)] px-3 py-1.5 text-sm font-medium text-[var(--mm-text)] disabled:opacity-50"
            disabled={busy || !scopeRow?.last_preview_run_uuid}
            onClick={() => void loadJsonFor(scopeRow?.last_preview_run_uuid)}
          >
            Load latest snapshot JSON
          </button>
          {isProvider && scopeRow?.last_preview_run_uuid ? (
            <button
              type="button"
              className="rounded-md border border-red-900/50 bg-red-950/30 px-3 py-1.5 text-sm font-medium text-red-100 disabled:opacity-50"
              disabled={busy}
              onClick={() => openApplyModal(scopeRow.last_preview_run_uuid!)}
            >
              Apply latest snapshot
            </button>
          ) : null}
        </div>
      ) : (
        <p className="text-sm text-[var(--mm-text2)]">Sign in as an operator to queue previews.</p>
      )}
      <div
        className="space-y-2 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3"
        data-testid="pruner-scope-scheduled-preview"
      >
        <h3 className="text-sm font-semibold text-[var(--mm-text)]">Scheduled preview ({props.scope})</h3>
        <p className="text-xs text-[var(--mm-text2)]">
          Each server instance has separate TV and Movies schedules. Interval: 60 seconds to 24 hours. The timestamp
          below updates only when the background scheduler queues a job for this {sectionWord} — not when you use the
          manual preview buttons. Scheduled runs use the <strong>missing primary art</strong> rule only; stale
          never-played previews are on-demand.
        </p>
        {showInteractiveControls ? (
          <>
            <label className="flex items-center gap-2 text-sm text-[var(--mm-text)]">
              <input
                type="checkbox"
                checked={schedEnabled}
                disabled={busy}
                onChange={(e) => setSchedEnabled(e.target.checked)}
              />
              Enable scheduled previews for this {sectionWord}
            </label>
            <div className="flex flex-wrap items-center gap-2">
              <label className="text-sm text-[var(--mm-text2)]">
                Every{" "}
                <input
                  type="number"
                  min={60}
                  max={86400}
                  className="w-28 rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-1 text-sm text-[var(--mm-text)]"
                  value={schedInterval}
                  disabled={busy}
                  onChange={(e) => setSchedInterval(parseInt(e.target.value, 10) || 3600)}
                />{" "}
                seconds
              </label>
              <button
                type="button"
                className="rounded-md bg-[var(--mm-accent)] px-3 py-1 text-sm font-medium text-white disabled:opacity-50"
                disabled={busy}
                onClick={() => void saveSchedule()}
              >
                Save schedule
              </button>
            </div>
            {schedMsg ? <p className="text-xs text-green-600">{schedMsg}</p> : null}
          </>
        ) : (
          <p className="text-sm text-[var(--mm-text2)]">
            Scheduled preview is <strong>{scopeRow?.scheduled_preview_enabled ? "on" : "off"}</strong>
            {scopeRow ? (
              <>
                {" "}
                (every {scopeRow.scheduled_preview_interval_seconds}s). Sign in as an operator to change it.
              </>
            ) : null}
          </p>
        )}
        <p className="text-xs text-[var(--mm-text2)]">
          Last scheduled enqueue:{" "}
          {scopeRow?.last_scheduled_preview_enqueued_at
            ? new Date(scopeRow.last_scheduled_preview_enqueued_at).toLocaleString()
            : "—"}
        </p>
      </div>
      {!isProvider ? (
      <div className="space-y-2" data-testid="pruner-preview-runs-history">
        <h3 className="text-sm font-semibold text-[var(--mm-text)]">Recent preview runs ({props.scope})</h3>
        {runsQuery.isLoading ? (
          <p className="text-sm text-[var(--mm-text2)]">Loading history…</p>
        ) : runsQuery.isError ? (
          <p className="text-sm text-red-600" role="alert">
            {(runsQuery.error as Error).message}
          </p>
        ) : runsQuery.data?.length ? (
          <div className="overflow-x-auto rounded-md border border-[var(--mm-border)]">
            <table className="w-full min-w-[32rem] border-collapse text-left text-sm text-[var(--mm-text)]">
              <thead className="border-b border-[var(--mm-border)] bg-[var(--mm-surface2)] text-xs uppercase text-[var(--mm-text2)]">
                <tr>
                  <th className="px-2 py-2">Run</th>
                  <th className="px-2 py-2">Rule</th>
                  <th className="px-2 py-2">When</th>
                  <th className="px-2 py-2">Outcome</th>
                  <th className="px-2 py-2">What it means</th>
                  <th className="px-2 py-2">Candidates</th>
                  <th className="px-2 py-2"> </th>
                </tr>
              </thead>
              <tbody>
                {runsQuery.data.map((row) => (
                  <tr key={row.preview_run_id} className="border-b border-[var(--mm-border)] align-top">
                    <td className="px-2 py-2 font-mono text-xs">{row.preview_run_id.slice(0, 8)}…</td>
                    <td className="px-2 py-2 text-xs text-[var(--mm-text2)]">{ruleFamilyColumnLabel(row.rule_family_id)}</td>
                    <td className="px-2 py-2 text-xs text-[var(--mm-text2)]">
                      {new Date(row.created_at).toLocaleString()}
                    </td>
                    <td className="px-2 py-2 text-xs">
                      <span className="font-medium">{row.outcome}</span>
                      {row.unsupported_detail ? (
                        <div className="mt-1 text-[var(--mm-text2)]">{row.unsupported_detail}</div>
                      ) : null}
                      {row.error_message ? (
                        <div className="mt-1 text-red-600">{row.error_message}</div>
                      ) : null}
                    </td>
                    <td
                      className="px-2 py-2 align-top text-[0.7rem] leading-snug text-[var(--mm-text2)]"
                      data-testid={`pruner-preview-run-caption-${row.preview_run_id}`}
                    >
                      {previewRunRowCaption(row)}
                    </td>
                    <td className="px-2 py-2 text-xs">
                      {row.candidate_count}
                      {row.truncated ? " (truncated)" : ""}
                    </td>
                    <td className="px-2 py-2 space-y-1">
                      <button
                        type="button"
                        className="rounded border border-[var(--mm-border)] px-2 py-1 text-xs font-medium text-[var(--mm-text)] disabled:opacity-50"
                        disabled={busy}
                        onClick={() => void loadJsonFor(row.preview_run_id)}
                      >
                        JSON
                      </button>
                      {canOperate && canApplyFromPreviewSnapshot(instance?.provider, row) ? (
                        <div>
                          <button
                            type="button"
                            className="mt-1 block w-full rounded border border-red-900/50 bg-red-950/30 px-2 py-1 text-left text-xs font-medium text-red-100 disabled:opacity-50"
                            data-testid={`pruner-apply-open-${row.preview_run_id}`}
                            disabled={busy}
                            onClick={() => openApplyModal(row.preview_run_id)}
                          >
                            {prunerApplyLabelForRuleFamily(row.rule_family_id)}
                          </button>
                        </div>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-[var(--mm-text2)]" data-testid="pruner-preview-runs-empty">
            No preview runs for this tab yet. Queue a preview from a rule panel above; when the worker finishes, rows
            appear here with outcome, candidate count, and a short explanation (including unsupported rules on Plex).
          </p>
        )}
      </div>
      ) : null}
      {applyModalRunId ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="pruner-apply-modal-title"
          data-testid="pruner-apply-modal"
        >
          <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-4 shadow-xl">
            <h3 id="pruner-apply-modal-title" className="text-base font-semibold text-[var(--mm-text)]">
              {applySnapshotOperatorLabel ?? "Apply from preview snapshot"}
            </h3>
            <p className="mt-2 text-sm text-[var(--mm-text2)]">
              This live action uses <strong>only</strong> the frozen candidate list from one preview snapshot. It does
              not re-run preview and does not widen the candidate set. Entries already removed at the provider are
              typically counted as skipped; successful removals follow the provider library API.
            </p>
            {applyEligQuery.isLoading ? (
              <p className="mt-3 text-sm text-[var(--mm-text2)]">Checking eligibility…</p>
            ) : applyEligQuery.isError ? (
              <p className="mt-3 text-sm text-red-600" role="alert">
                {(applyEligQuery.error as Error).message}
              </p>
            ) : applyEligQuery.data ? (
              <ul className="mt-3 list-inside list-disc space-y-1 text-sm text-[var(--mm-text)]">
                <li>
                  Server: <strong>{applyEligQuery.data.display_name}</strong> ({applyEligQuery.data.provider})
                </li>
                <li>
                  Scope: <strong>{applyEligQuery.data.media_scope === "tv" ? "TV" : "Movies"}</strong>
                </li>
                <li>
                  Preview time:{" "}
                  {applyEligQuery.data.preview_created_at
                    ? new Date(applyEligQuery.data.preview_created_at).toLocaleString()
                    : "—"}
                </li>
                <li>
                  Snapshot id: <span className="font-mono text-xs">{applyEligQuery.data.preview_run_id}</span>
                </li>
                <li>
                  Candidates in snapshot: <strong>{applyEligQuery.data.candidate_count}</strong>
                </li>
              </ul>
            ) : null}
            {applyEligQuery.data && !applyEligQuery.data.eligible ? (
              <p className="mt-3 text-sm text-amber-700" role="status">
                {applyEligQuery.data.reasons.length
                  ? applyEligQuery.data.reasons.join(" ")
                  : "This snapshot cannot be applied right now."}
              </p>
            ) : null}
            {applyEligQuery.data?.eligible ? (
              <label className="mt-4 flex cursor-pointer items-start gap-2 text-sm text-[var(--mm-text)]">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={applySnapshotConfirmed}
                  onChange={(e) => setApplySnapshotConfirmed(e.target.checked)}
                />
                <span>
                  I confirm <strong>{applySnapshotOperatorLabel}</strong> for this exact preview snapshot only (
                  {applyModalRunId.slice(0, 8)}…), with at most {applyEligQuery.data.candidate_count} library entries.
                </span>
              </label>
            ) : null}
            <div className="mt-4 flex flex-wrap justify-end gap-2">
              <button
                type="button"
                className="rounded-md border border-[var(--mm-border)] px-3 py-1.5 text-sm font-medium text-[var(--mm-text)]"
                onClick={() => closeApplyModal()}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded-md bg-red-800 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                data-testid="pruner-apply-confirm"
                disabled={
                  busy ||
                  !applyEligQuery.data?.eligible ||
                  !applySnapshotConfirmed ||
                  applyEligQuery.isLoading ||
                  applyEligQuery.isError
                }
                onClick={() => void confirmApplyFromSnapshot()}
              >
                {applySnapshotOperatorLabel ?? "Confirm apply"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {err ? (
        <p className="text-sm text-red-600" role="alert">
          {err}
        </p>
      ) : null}
      {preview ? <p className="text-sm text-[var(--mm-text)]">{preview}</p> : null}
      {jsonPreview ? (
        <pre className="max-h-96 overflow-auto rounded-md border border-[var(--mm-border)] bg-[var(--mm-surface2)] p-3 text-xs">
          {jsonPreview}
        </pre>
      ) : null}
      </fieldset>
    </section>
  );
}
