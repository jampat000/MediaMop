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

export function PrunerScopeTab(props: { scope: "tv" | "movies" }) {
  const { instanceId, instance } = useOutletContext<Ctx>();
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
  const canOperate = me.data?.role === "admin" || me.data?.role === "operator";

  const scopeRow = instance?.scopes.find((s) => s.media_scope === props.scope);
  const label = props.scope === "tv" ? "TV (episodes)" : "Movies (one row per movie item)";
  const isPlex = instance?.provider === "plex";

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
    enabled: Boolean(instanceId),
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
      setSchedMsg("Saved. This schedule applies only to this server and this tab (TV or Movies).");
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
      setStaleNeverMsg("Saved never-played rule settings for this tab only.");
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
          ? "Saved genre include list for this tab only (previews use it; apply still uses the frozen snapshot only)."
          : "Cleared genre filters for this tab.",
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
          ? "Saved people include list for this tab only (previews only; apply still uses the frozen snapshot)."
          : "Cleared people filters for this tab.",
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
        "Saved preview year bounds for this tab (Jellyfin/Emby: ProductionYear; Plex allLeaves movie rows: leaf year when present).",
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
          ? "Saved studio include list for this tab (Jellyfin/Emby: Studios on Items; Plex: Studio tags on missing-primary leaves)."
          : "Cleared studio preview filters for this tab.",
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
          ? "Saved collection include list (Plex allLeaves movie previews on this tab)."
          : "Cleared collection preview filters for this tab.",
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
      setWatchedMoviesMsg("Saved watched movies rule for this Movies tab and server instance only.");
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
          ? "Saved watched low-rating movies rule for this Movies tab (Plex leaf audienceRating vs your saved Plex audienceRating ceiling, 0–10)."
          : "Saved watched low-rating movies rule for this Movies tab (Jellyfin/Emby Items CommunityRating vs your saved CommunityRating ceiling, 0–10).",
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
          ? "Saved unwatched stale movies rule for this Movies tab (Plex: unwatched leaves by viewCount/lastViewedAt plus addedAt age)."
          : "Saved unwatched stale movies rule for this Movies tab (library DateCreated age).",
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
      setWatchedTvMsg("Saved watched TV rule for this TV tab and server instance only.");
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

  return (
    <section className="max-w-3xl space-y-3" aria-labelledby="pruner-scope-heading">
      <h2 id="pruner-scope-heading" className="text-base font-semibold text-[var(--mm-text)]">
        {label}
      </h2>
      <div
        className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-surface2)]/40 px-4 py-3 text-xs text-[var(--mm-text2)] sm:text-sm"
        data-testid="pruner-scope-trust-banner"
      >
        <p>
          <strong className="text-[var(--mm-text)]">Previews</strong> collect candidates you can inspect (including JSON).
          <strong className="text-[var(--mm-text)]"> Apply</strong> always uses the{" "}
          <strong className="text-[var(--mm-text)]">selected preview snapshot only</strong>. It does not re-scan the
          library, widen the list, or re-run narrowing filters from this tab.
        </p>
      </div>
      {!isPlex ? (
        <p className="text-sm text-[var(--mm-text2)]">
          {props.scope === "tv"
            ? "Previews list episodes missing a primary image (episode-level rows only), or episodes that are unplayed for the MediaMop token and older than your age threshold by library DateCreated — each rule has its own preview queue."
            : "Previews list movie items missing a primary image (one row per movie), movies the server marks watched for the MediaMop token, or movies that are unplayed and older than your age threshold by library DateCreated — each rule has its own preview queue."}
        </p>
      ) : (
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
      )}
      {isPlex && scopeRow ? (
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
      {scopeRow ? (
        <div
          className="space-y-2 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
          data-testid="pruner-genre-filters-panel"
        >
          <p className="text-sm font-semibold text-[var(--mm-text)]">Optional preview genre include (this tab only)</p>
          <p className="text-xs text-[var(--mm-text2)]">
            Comma-separated names. When set, preview jobs on this tab only return items whose server-reported genres
            include a case-insensitive match for at least one listed name. This narrows preview collection only — apply
            still deletes exactly the IDs in the saved snapshot.
          </p>
          <p className="text-xs text-[var(--mm-text2)]">
            {isPlex
              ? "Plex: genre filters apply to every preview on this tab that reads allLeaves (missing-primary, watched movies, low-rating, unwatched stale) using Genre tags on each leaf."
              : "Jellyfin / Emby: uses each item’s Genres field from the Items API for every preview rule on this tab."}
          </p>
          {isPlex ? (
            <p
              className="text-xs text-amber-100/90"
              data-testid="pruner-plex-genre-empty-preview-note"
            >
              If a preview finishes successfully with <strong>zero rows</strong> while filters are set, that usually
              means nothing in this pass matched the rule under those genres — not that Plex reports nothing to clean.
              Matching uses Genre tags on each <code className="text-[0.85em]">allLeaves</code> leaf only.
            </p>
          ) : null}
          {canOperate ? (
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
          <p className="text-sm font-semibold text-[var(--mm-text)]">Optional preview people include (this tab only)</p>
          <p className="text-xs text-[var(--mm-text2)]">
            Comma-separated <strong>person names</strong> (one full name per entry). Preview keeps only items where at
            least one server-reported name matches one entry, using exact case-insensitive equality after trimming. This
            narrows preview collection only — apply still deletes exactly the IDs in the saved snapshot.
          </p>
          {isPlex ? (
            <p className="text-xs text-[var(--mm-text2)]" data-testid="pruner-people-plex-note">
              Plex: applies to previews that read <code className="text-[0.85em]">allLeaves</code> on this tab (missing
              primary art, watched movies, low-rating, unwatched stale). Names come from <strong>Role</strong>,{" "}
              <strong>Writer</strong>, and <strong>Director</strong> tag strings on each leaf (no separate metadata fetch).
            </p>
          ) : (
            <p className="text-xs text-[var(--mm-text2)]" data-testid="pruner-people-jf-emby-note">
              Jellyfin / Emby: uses each item&apos;s <strong>People</strong> list from the Items API when filters are
              saved (MediaMop requests explicit Fields). Applies to every preview rule on this tab.
            </p>
          )}
          {canOperate ? (
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
          <p className="text-sm font-semibold text-[var(--mm-text)]">Optional preview year range (this tab only)</p>
          <p className="text-xs text-[var(--mm-text2)]">
            Leave a box empty to leave that side open. When either bound is set, items with <strong>no</strong>{" "}
            provider-reported year never match. Jellyfin/Emby use <code className="text-[0.85em]">ProductionYear</code>{" "}
            on Items; Plex uses each movie leaf&apos;s <code className="text-[0.85em]">year</code> when the server sends
            it on <code className="text-[0.85em]">allLeaves</code> rows (missing-primary and movie rules on the Movies
            tab). Inclusive {1900}–{2100}.
          </p>
          {canOperate ? (
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
          <p className="text-sm font-semibold text-[var(--mm-text)]">Optional preview studio include (this tab only)</p>
          <p className="text-xs text-[var(--mm-text2)]">
            Comma-separated studio names — exact case-insensitive match against Jellyfin/Emby{" "}
            <code className="text-[0.85em]">Studios</code> or Plex <code className="text-[0.85em]">Studio</code> tags (and
            top-level <code className="text-[0.85em]">studio</code> string when present) on Plex <code className="text-[0.85em]">allLeaves</code>{" "}
            movie rows. This is <strong>not</strong> a separate “network” filter; only provider-native studio fields are
            used.
          </p>
          {canOperate ? (
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
          <p className="text-xs text-[var(--mm-text2)]">
            Comma-separated collection names — exact match against <code className="text-[0.85em]">Collection</code>{" "}
            tags on each <code className="text-[0.85em]">allLeaves</code> movie row (missing-primary and movie rules on
            this tab). Jellyfin/Emby previews do <strong>not</strong> apply this list (no honest per-item collection field
            on the Items path used here).
          </p>
          {canOperate ? (
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
          className="rounded-md border border-amber-600/40 bg-amber-950/20 px-3 py-2 text-sm text-[var(--mm-text)]"
          role="status"
          data-testid="pruner-plex-other-rules-note"
        >
          <p className="font-medium text-amber-100">Other Pruner rules on Plex (this tab)</p>
          <p className="mt-1 text-xs text-[var(--mm-text2)]">
            {props.scope === "movies" ? (
              <>
                Stale never-played and watched-TV previews are <strong>not</strong> implemented for Plex. Movie-tab
                rules for watched movies, watched low-rating movies (<code className="text-[0.85em]">audienceRating</code>
                ), and unwatched stale movies (<code className="text-[0.85em]">addedAt</code>) use{" "}
                <code className="text-[0.85em]">allLeaves</code> with your token — see the panels below.
              </>
            ) : (
              <>
                Stale never-played and watched-TV previews are <strong>not</strong> implemented for Plex here. Queueing
                those rule previews still records an explicit unsupported outcome for traceability.
              </>
            )}
          </p>
        </div>
      ) : null}
      {!isPlex ? (
        <Fragment>
        <div
          className="space-y-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
          data-testid="pruner-never-played-stale-panel"
        >
          <p className="text-sm font-semibold text-[var(--mm-text)]">Stale never-played (Jellyfin / Emby)</p>
          <p className="text-xs text-[var(--mm-text2)]">
            Candidates are library items with <strong>no play state</strong> for the MediaMop server user (Jellyfin /
            Emby user data) and a <strong>DateCreated</strong> older than the minimum age below. This tab (TV or
            Movies) and this server instance only — nothing global.
          </p>
          <p className="text-xs text-[var(--mm-text2)]">
            Apply (when enabled) removes those library entries via the provider API for the frozen preview list only —
            MediaMop does not claim whether underlying media files are deleted; that is provider behavior.
          </p>
          {canOperate ? (
            <div className="space-y-2">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={staleNeverEnabled}
                  disabled={busy}
                  onChange={(e) => setStaleNeverEnabled(e.target.checked)}
                />
                Enable stale never-played rule for this tab
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
                Queue preview (stale never-played)
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
            className="space-y-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
            data-testid="pruner-watched-tv-panel"
          >
            <p className="text-sm font-semibold text-[var(--mm-text)]">Watched TV (Jellyfin / Emby, TV tab only)</p>
            <p className="text-xs text-[var(--mm-text2)]">
              Candidates are <strong>episodes</strong> the server reports as <strong>watched</strong> for the MediaMop
              library user (same API token as other Pruner rules). Movies are not in this pass — use the Movies tab for
              other rules. This server instance only.
            </p>
            <p className="text-xs text-[var(--mm-text2)]">
              Preview is the dry run; apply uses the frozen list only. Removal goes through the provider library API —
              MediaMop does not claim whether media files on disk are removed.
            </p>
            {canOperate ? (
              <div className="space-y-2">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={watchedTvEnabled}
                    disabled={busy}
                    onChange={(e) => setWatchedTvEnabled(e.target.checked)}
                  />
                  Enable watched TV rule for this TV tab
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
                Watched TV rule is <strong>{scopeRow?.watched_tv_reported_enabled ? "on" : "off"}</strong> for this tab.
                Sign in as an operator to change it.
              </p>
            )}
          </div>
        ) : null}
        </Fragment>
      ) : null}
      {!isPlex ? null : props.scope === "movies" ? (
        <p className="text-xs text-[var(--mm-text2)]">
          Watched / low-rating / unwatched stale movie previews on Plex use the same{" "}
          <code className="text-[0.85em]">allLeaves</code> token-scoped metadata as other Plex previews: watched means{" "}
          <code className="text-[0.85em]">viewCount</code> ≥ 1 or a positive <code className="text-[0.85em]">lastViewedAt</code>
          ; low-rating compares your saved Plex audienceRating ceiling to leaf <code className="text-[0.85em]">audienceRating</code>{" "}
          (not Jellyfin/Emby <code className="text-[0.85em]">CommunityRating</code>); stale unwatched uses library{" "}
          <code className="text-[0.85em]">addedAt</code> age, not <code className="text-[0.85em]">DateCreated</code>.
        </p>
      ) : null}
      {props.scope === "movies" ? (
          <>
            <div
              className="space-y-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
              data-testid="pruner-watched-movies-panel"
            >
              <p className="text-sm font-semibold text-[var(--mm-text)]">
                {isPlex ? "Watched movies (Plex, Movies tab only)" : "Watched movies (Jellyfin / Emby, Movies tab only)"}
              </p>
              <p className="text-xs text-[var(--mm-text2)]">
                {isPlex ? (
                  <>
                    Candidates are <strong>movie</strong> leaves from <code className="text-[0.85em]">allLeaves</code>{" "}
                    where Plex reports <code className="text-[0.85em]">viewCount</code> ≥ 1 or a positive{" "}
                    <code className="text-[0.85em]">lastViewedAt</code> for the same <code className="text-[0.85em]">X-Plex-Token</code>{" "}
                    as other Pruner Plex reads (no separate account API).
                  </>
                ) : (
                  <>
                    Candidates are <strong>movie library items</strong> the server reports as <strong>watched</strong> for
                    the MediaMop library user (same API token as other Pruner rules). TV episodes are not in this pass —
                    use the TV tab for watched TV. This server instance only.
                  </>
                )}
              </p>
              <p className="text-xs text-[var(--mm-text2)]">
                Preview is the dry run; apply uses the frozen list only. Removal goes through the provider library API —
                MediaMop does not claim whether media files on disk are removed.
              </p>
              {canOperate ? (
                <div className="space-y-2">
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={watchedMoviesEnabled}
                      disabled={busy}
                      onChange={(e) => setWatchedMoviesEnabled(e.target.checked)}
                    />
                    Enable watched movies rule for this Movies tab
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
              className="space-y-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
              data-testid="pruner-watched-low-rating-panel"
            >
              <p className="text-sm font-semibold text-[var(--mm-text)]">
                {isPlex
                  ? "Watched low-rating movies (Plex, Movies tab only)"
                  : "Watched low-rating movies (Jellyfin / Emby, Movies tab only)"}
              </p>
              <p className="text-xs text-[var(--mm-text2)]">
                {isPlex ? (
                  <>
                    Candidates are <strong>watched</strong> movie leaves (same watched test as watched movies above)
                    whose Plex <strong>audienceRating</strong> is at or below the numeric ceiling you save for this server
                    (stored as <code className="text-[0.85em]">watched_movie_low_rating_max_plex_audience_rating</code> — separate
                    from the Jellyfin/Emby CommunityRating ceiling). Items with no numeric audience rating are skipped.
                  </>
                ) : (
                  <>
                    Candidates are <strong>watched</strong> movie library items whose Jellyfin/Emby{" "}
                    <strong>CommunityRating</strong> is at or below the ceiling you save for this server (
                    <code className="text-[0.85em]">watched_movie_low_rating_max_jellyfin_emby_community_rating</code>, 0–10 on
                    that field). MediaMop does not remap it to stars or another scale. Items with no rating are skipped.
                    Genre and people filters narrow previews only (AND when both are set).
                  </>
                )}
              </p>
              {canOperate ? (
                <div className="space-y-2">
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={lowRatingEnabled}
                      disabled={busy}
                      onChange={(e) => setLowRatingEnabled(e.target.checked)}
                    />
                    Enable watched low-rating movies rule for this Movies tab
                  </label>
                  <label className="flex flex-wrap items-center gap-2 text-sm text-[var(--mm-text2)]">
                    {isPlex
                      ? "Max audienceRating ceiling — Plex movie leaves (0–10 inclusive)"
                      : "Max CommunityRating ceiling — Jellyfin/Emby Items (0–10 inclusive)"}
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
              className="space-y-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
              data-testid="pruner-unwatched-stale-panel"
            >
              <p className="text-sm font-semibold text-[var(--mm-text)]">
                {isPlex
                  ? "Unwatched stale movies (Plex, Movies tab only)"
                  : "Unwatched stale movies (Jellyfin / Emby, Movies tab only)"}
              </p>
              <p className="text-xs text-[var(--mm-text2)]">
                {isPlex ? (
                  <>
                    Candidates are <strong>unwatched</strong> movie leaves (no positive play signal from{" "}
                    <code className="text-[0.85em]">viewCount</code>/<code className="text-[0.85em]">lastViewedAt</code>
                    ) whose library <strong>addedAt</strong> timestamp is older than the minimum age. This is{" "}
                    <strong>not</strong> Jellyfin/Emby <code className="text-[0.85em]">DateCreated</code> semantics.
                  </>
                ) : (
                  <>
                    Candidates are <strong>unwatched</strong> movie items (user play state for this API token) whose library{" "}
                    <strong>DateCreated</strong> is older than the minimum age. This is not “not recently watched” — only
                    items with no watched/play state. Genre and people filters narrow previews only.
                  </>
                )}
              </p>
              {canOperate ? (
                <div className="space-y-2">
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={unwatchedStaleEnabled}
                      disabled={busy}
                      onChange={(e) => setUnwatchedStaleEnabled(e.target.checked)}
                    />
                    Enable unwatched stale movies rule for this Movies tab
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
      {scopeRow ? (
        <div
          className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text2)]"
          data-testid="pruner-scope-latest-preview-summary"
        >
          <h3 className="text-sm font-semibold text-[var(--mm-text)]">Latest preview job (this tab)</h3>
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
      {canOperate ? (
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
            Load candidates JSON (latest summary)
          </button>
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
          below updates only when the background scheduler queues a job for this tab — not when you use the manual
          preview buttons. Scheduled runs use the <strong>missing primary art</strong> rule only; stale never-played
          previews are on-demand.
        </p>
        {canOperate ? (
          <>
            <label className="flex items-center gap-2 text-sm text-[var(--mm-text)]">
              <input
                type="checkbox"
                checked={schedEnabled}
                disabled={busy}
                onChange={(e) => setSchedEnabled(e.target.checked)}
              />
              Enable scheduled previews for this tab
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
    </section>
  );
}
