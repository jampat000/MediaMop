import { useEffect, useState } from "react";
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
import { finalizePrunerRunIntervalMinutesDraft } from "../../lib/ui/pruner-schedule-interval";
import { prunerGenresFromApi } from "./pruner-genre-multi-select";
import {
  normalizePeopleRolesFromApi,
  peopleRolesForPlexPersist,
  peopleRolesForPlexUiState,
  type PrunerPeopleRoleId,
} from "./pruner-people-roles";
import { useAppDateFormatter } from "../../lib/ui/mm-format-date";

export type Ctx = {
  instanceId: number;
  instance: PrunerServerInstance | undefined;
};

export type PrunerScopeTabProps = {
  scope: "tv" | "movies";
  contextOverride?: Ctx;
  disabledMode?: boolean;
  variant?: "default" | "provider";
  providerSubSection?: "rules" | "filters" | "people";
};

export function usePrunerScopeTabController(props: PrunerScopeTabProps) {
  const outletCtx = useOutletContext<Ctx>();
  const { instanceId, instance } = props.contextOverride ?? outletCtx;
  const me = useMeQuery();
  const fmt = useAppDateFormatter();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [jsonPreview, setJsonPreview] = useState<string | null>(null);
  const [schedEnabled, setSchedEnabled] = useState(false);
  const [schedIntervalSec, setSchedIntervalSec] = useState(3600);
  const [schedIntervalMinDraft, setSchedIntervalMinDraft] = useState<
    string | null
  >(null);
  const [schedHoursLimited, setSchedHoursLimited] = useState(false);
  const [schedDays, setSchedDays] = useState("");
  const [schedStart, setSchedStart] = useState("00:00");
  const [schedEnd, setSchedEnd] = useState("23:59");
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
  const [unwatchedStaleMsg, setUnwatchedStaleMsg] = useState<string | null>(
    null,
  );
  const [genreSelection, setGenreSelection] = useState<string[]>([]);
  const [genreMsg, setGenreMsg] = useState<string | null>(null);
  const [peopleText, setPeopleText] = useState("");
  const [peopleRoles, setPeopleRoles] = useState<PrunerPeopleRoleId[]>([]);
  const [peopleMsg, setPeopleMsg] = useState<string | null>(null);
  const [yearMinStr, setYearMinStr] = useState("");
  const [yearMaxStr, setYearMaxStr] = useState("");
  const [yearMsg, setYearMsg] = useState<string | null>(null);
  const [studioText, setStudioText] = useState("");
  const [studioMsg, setStudioMsg] = useState<string | null>(null);
  const [collectionText, setCollectionText] = useState("");
  const [collectionMsg, setCollectionMsg] = useState<string | null>(null);
  const [previewMaxItems, setPreviewMaxItems] = useState(500);
  const [previewMaxItemsMsg, setPreviewMaxItemsMsg] = useState<string | null>(
    null,
  );
  const [bundleMsg, setBundleMsg] = useState<string | null>(null);
  /** Provider Rules: single inputs (0 = off) mapped to never-played / low-rating / unwatched stale. */
  const [rulesTvOlderDaysStr, setRulesTvOlderDaysStr] = useState("0");
  const [rulesMoviesLowRatingStr, setRulesMoviesLowRatingStr] = useState("0");
  const [rulesMoviesUnwatchedDaysStr, setRulesMoviesUnwatchedDaysStr] =
    useState("0");
  const isProvider = props.variant === "provider";
  const provSub = props.providerSubSection;
  const canOperate = me.data?.role === "admin" || me.data?.role === "operator";
  const showInteractiveControls = canOperate || Boolean(props.disabledMode);

  const scopeRow = instance?.scopes.find((s) => s.media_scope === props.scope);
  const label = props.scope === "tv" ? "TV shows" : "Movies";
  const isPlex = instance?.provider === "plex";
  const libraryTabPhrase = props.scope === "tv" ? "TV tab" : "Movies tab";

  function ruleFamilyColumnLabel(id: string): string {
    if (id === RULE_FAMILY_WATCHED_TV_REPORTED)
      return "Delete watched TV episodes";
    if (id === RULE_FAMILY_WATCHED_MOVIES_REPORTED)
      return "Delete watched movies";
    if (id === RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED)
      return "Delete watched movies below your score";
    if (id === RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED)
      return "Delete unwatched movies older than your age setting";
    if (id === RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED)
      return "Delete never-started TV or movies older than your age setting";
    if (id === RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED)
      return "Delete items missing a main poster or episode image";
    return "This cleanup type";
  }

  const previewRunsQueryKey = [
    "pruner",
    "preview-runs",
    instanceId,
    props.scope,
  ] as const;
  const runsQuery = useQuery({
    queryKey: previewRunsQueryKey,
    queryFn: () =>
      fetchPrunerPreviewRuns(instanceId, {
        media_scope: props.scope,
        limit: 25,
      }),
    enabled: !isProvider && Boolean(instanceId),
  });

  const applyEligQuery = useQuery({
    queryKey: [
      "pruner",
      "apply-eligibility",
      instanceId,
      props.scope,
      applyModalRunId,
    ] as const,
    queryFn: () =>
      fetchPrunerApplyEligibility(instanceId, props.scope, applyModalRunId!),
    enabled: Boolean(instanceId && applyModalRunId),
  });

  const applySnapshotOperatorLabel = applyEligQuery.data
    ? applyEligQuery.data.apply_operator_label ||
      prunerApplyLabelForRuleFamily(applyEligQuery.data.rule_family_id)
    : null;

  useEffect(() => {
    if (!scopeRow) return;
    setSchedEnabled(scopeRow.scheduled_preview_enabled);
    setSchedIntervalSec(scopeRow.scheduled_preview_interval_seconds);
    setSchedIntervalMinDraft(null);
    setSchedHoursLimited(scopeRow.scheduled_preview_hours_limited ?? false);
    setSchedDays(scopeRow.scheduled_preview_days ?? "");
    setSchedStart(scopeRow.scheduled_preview_start ?? "00:00");
    setSchedEnd(scopeRow.scheduled_preview_end ?? "23:59");
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
    setGenreSelection(prunerGenresFromApi(scopeRow.preview_include_genres));
    setPeopleText((scopeRow.preview_include_people ?? []).join(", "));
    setPeopleRoles(
      isPlex
        ? peopleRolesForPlexUiState(scopeRow.preview_include_people_roles)
        : normalizePeopleRolesFromApi(scopeRow.preview_include_people_roles),
    );
    setYearMinStr(
      scopeRow.preview_year_min != null
        ? String(scopeRow.preview_year_min)
        : "",
    );
    setYearMaxStr(
      scopeRow.preview_year_max != null
        ? String(scopeRow.preview_year_max)
        : "",
    );
    setStudioText((scopeRow.preview_include_studios ?? []).join(", "));
    setCollectionText((scopeRow.preview_include_collections ?? []).join(", "));
    setPreviewMaxItems(scopeRow.preview_max_items);
    if (props.scope === "tv") {
      setRulesTvOlderDaysStr(
        !scopeRow.never_played_stale_reported_enabled
          ? "0"
          : String(scopeRow.never_played_min_age_days),
      );
    }
    if (props.scope === "movies") {
      setRulesMoviesLowRatingStr(
        !scopeRow.watched_movie_low_rating_reported_enabled
          ? "0"
          : String(
              isPlex
                ? scopeRow.watched_movie_low_rating_max_plex_audience_rating
                : scopeRow.watched_movie_low_rating_max_jellyfin_emby_community_rating,
            ),
      );
      setRulesMoviesUnwatchedDaysStr(
        !scopeRow.unwatched_movie_stale_reported_enabled
          ? "0"
          : String(scopeRow.unwatched_movie_stale_min_age_days),
      );
    }
  }, [
    scopeRow,
    scopeRow?.scheduled_preview_enabled,
    scopeRow?.scheduled_preview_interval_seconds,
    scopeRow?.scheduled_preview_hours_limited,
    scopeRow?.scheduled_preview_days,
    scopeRow?.scheduled_preview_start,
    scopeRow?.scheduled_preview_end,
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
    scopeRow?.preview_include_people_roles,
    scopeRow?.preview_year_min,
    scopeRow?.preview_year_max,
    scopeRow?.preview_include_studios,
    scopeRow?.preview_include_collections,
    scopeRow?.preview_max_items,
    scopeRow?.media_scope,
    instanceId,
    props.scope,
  ]);

  async function saveSchedule() {
    setSchedMsg(null);
    setErr(null);
    setBusy(true);
    try {
      const csrf_token = await fetchCsrfToken();
      const resolvedSec =
        schedIntervalMinDraft !== null
          ? finalizePrunerRunIntervalMinutesDraft(
              schedIntervalMinDraft,
              schedIntervalSec,
            )
          : schedIntervalSec;
      const iv = Math.max(60, Math.min(86400, resolvedSec));
      await patchPrunerScope(instanceId, props.scope, {
        scheduled_preview_enabled: schedEnabled,
        scheduled_preview_interval_seconds: iv,
        scheduled_preview_hours_limited: schedHoursLimited,
        scheduled_preview_days: schedDays,
        scheduled_preview_start: schedStart,
        scheduled_preview_end: schedEnd,
        csrf_token,
      });
      setSchedIntervalMinDraft(null);
      setSchedIntervalSec(iv);
      await qc.invalidateQueries({
        queryKey: ["pruner", "instances", instanceId],
      });
      setSchedMsg(
        `Saved. Automatic scans use this server’s ${libraryTabPhrase} only.`,
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
      await qc.invalidateQueries({
        queryKey: ["pruner", "instances", instanceId],
      });
      setPreviewMaxItemsMsg(
        "Saved how many items each scan may check for this library.",
      );
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
      await qc.invalidateQueries({
        queryKey: ["pruner", "instances", instanceId],
      });
      setStaleNeverMsg(
        "Saved never-watched TV and movie age settings for this library.",
      );
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
      const tokens = [...genreSelection];
      await patchPrunerScope(instanceId, props.scope, {
        preview_include_genres: tokens,
        csrf_token,
      });
      await qc.invalidateQueries({
        queryKey: ["pruner", "instances", instanceId],
      });
      setGenreMsg(
        tokens.length
          ? "Saved your genre picks for this library."
          : "Cleared genre picks — all genres will be included in scans.",
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
        preview_include_people_roles: isPlex
          ? peopleRolesForPlexPersist(peopleRoles)
          : [...peopleRoles],
        csrf_token,
      });
      await qc.invalidateQueries({
        queryKey: ["pruner", "instances", instanceId],
      });
      setPeopleMsg(
        tokens.length
          ? "Saved name filters for this library."
          : "Cleared name filters for this library.",
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
        setErr(
          "Each year must be a whole number between 1900 and 2100, or left empty.",
        );
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
      await qc.invalidateQueries({
        queryKey: ["pruner", "instances", instanceId],
      });
      setYearMsg("Saved release year limits for this library.");
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
      await qc.invalidateQueries({
        queryKey: ["pruner", "instances", instanceId],
      });
      setStudioMsg(
        tokens.length
          ? "Saved studio filters for this library."
          : "Cleared studio filters for this library.",
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
      await qc.invalidateQueries({
        queryKey: ["pruner", "instances", instanceId],
      });
      setCollectionMsg(
        tokens.length
          ? "Saved collection filters for this library."
          : "Cleared collection filters for this library.",
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
      await qc.invalidateQueries({
        queryKey: ["pruner", "instances", instanceId],
      });
      setWatchedMoviesMsg(
        "Saved watched-movie cleanup setting for this library.",
      );
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
      const cap = Math.max(
        0,
        Math.min(10, Number.parseFloat(lowRatingMax) || 4),
      );
      await patchPrunerScope(instanceId, props.scope, {
        watched_movie_low_rating_reported_enabled: lowRatingEnabled,
        ...(instance?.provider === "plex"
          ? { watched_movie_low_rating_max_plex_audience_rating: cap }
          : {
              watched_movie_low_rating_max_jellyfin_emby_community_rating: cap,
            }),
        csrf_token,
      });
      await qc.invalidateQueries({
        queryKey: ["pruner", "instances", instanceId],
      });
      setLowRatingMsg(
        instance?.provider === "plex"
          ? "Saved low-score watched-movie setting (Plex audience rating)."
          : "Saved low-score watched-movie setting (server community rating).",
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
      await qc.invalidateQueries({
        queryKey: ["pruner", "instances", instanceId],
      });
      setUnwatchedStaleMsg(
        instance?.provider === "plex"
          ? "Saved old unwatched movie setting (uses when Plex says the title was added)."
          : "Saved old unwatched movie setting (uses when the server says the title was created).",
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
      await qc.invalidateQueries({
        queryKey: ["pruner", "instances", instanceId],
      });
      setWatchedTvMsg("Saved watched-TV cleanup setting for this library.");
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
      await postPrunerPreview(instanceId, props.scope);
      await qc.invalidateQueries({
        queryKey: ["pruner", "instances", instanceId],
      });
      await qc.invalidateQueries({ queryKey: previewRunsQueryKey });
      setPreview(
        "Scan for broken posters and images started. The table below updates when results are ready.",
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
      await postPrunerPreview(instanceId, props.scope, {
        rule_family_id: RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED,
      });
      await qc.invalidateQueries({
        queryKey: ["pruner", "instances", instanceId],
      });
      await qc.invalidateQueries({ queryKey: previewRunsQueryKey });
      setPreview(
        "Scan for unwatched TV or movies older than your setting started. The table below updates when ready.",
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
      await postPrunerPreview(instanceId, props.scope, {
        rule_family_id: RULE_FAMILY_WATCHED_MOVIES_REPORTED,
      });
      await qc.invalidateQueries({
        queryKey: ["pruner", "instances", instanceId],
      });
      await qc.invalidateQueries({ queryKey: previewRunsQueryKey });
      setPreview(
        "Scan for watched movies started. The table below updates when ready.",
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
      await postPrunerPreview(instanceId, props.scope, {
        rule_family_id: RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED,
      });
      await qc.invalidateQueries({
        queryKey: ["pruner", "instances", instanceId],
      });
      await qc.invalidateQueries({ queryKey: previewRunsQueryKey });
      setPreview(
        "Scan for low-score watched movies started. The table below updates when ready.",
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
      await postPrunerPreview(instanceId, props.scope, {
        rule_family_id: RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED,
      });
      await qc.invalidateQueries({
        queryKey: ["pruner", "instances", instanceId],
      });
      await qc.invalidateQueries({ queryKey: previewRunsQueryKey });
      setPreview(
        "Scan for old unwatched movies started. The table below updates when ready.",
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
      await postPrunerPreview(instanceId, props.scope, {
        rule_family_id: RULE_FAMILY_WATCHED_TV_REPORTED,
      });
      await qc.invalidateQueries({
        queryKey: ["pruner", "instances", instanceId],
      });
      await qc.invalidateQueries({ queryKey: previewRunsQueryKey });
      setPreview(
        "Scan for watched TV shows started. The table below updates when ready.",
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
      elig.apply_operator_label ||
      prunerApplyLabelForRuleFamily(elig.rule_family_id);
    setErr(null);
    setBusy(true);
    try {
      await postPrunerApplyFromPreview(instanceId, props.scope, runId);
      await qc.invalidateQueries({ queryKey: previewRunsQueryKey });
      await qc.invalidateQueries({ queryKey: ["activity"] });
      closeApplyModal();
      setPreview(
        `Deletion started (${opLabel}). Check Activity for removed, skipped, and failed counts.`,
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
      setErr("Pick a finished scan from the history table first.");
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
      const raw = parseInt(rulesTvOlderDaysStr.trim(), 10);
      const tvStaleOn = Number.isFinite(raw) && raw >= 7;
      const tvStaleDays = tvStaleOn ? Math.max(7, Math.min(3650, raw)) : 90;
      await patchPrunerScope(instanceId, "tv", {
        watched_tv_reported_enabled: watchedTvEnabled,
        never_played_stale_reported_enabled: tvStaleOn,
        never_played_min_age_days: tvStaleDays,
        csrf_token,
      });
      await qc.invalidateQueries({
        queryKey: ["pruner", "instances", instanceId],
      });
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
      const lowRaw = Number.parseFloat(rulesMoviesLowRatingStr.trim());
      const lowOn = Number.isFinite(lowRaw) && lowRaw > 0;
      const cap = lowOn ? Math.max(0, Math.min(10, lowRaw)) : 4;
      const uwRaw = parseInt(rulesMoviesUnwatchedDaysStr.trim(), 10);
      const uwOn = Number.isFinite(uwRaw) && uwRaw >= 7;
      const uwDays = uwOn ? Math.max(7, Math.min(3650, uwRaw)) : 90;
      await patchPrunerScope(instanceId, "movies", {
        watched_movies_reported_enabled: watchedMoviesEnabled,
        watched_movie_low_rating_reported_enabled: lowOn,
        ...(instance?.provider === "plex"
          ? { watched_movie_low_rating_max_plex_audience_rating: cap }
          : {
              watched_movie_low_rating_max_jellyfin_emby_community_rating: cap,
            }),
        unwatched_movie_stale_reported_enabled: uwOn,
        unwatched_movie_stale_min_age_days: uwDays,
        csrf_token,
      });
      await qc.invalidateQueries({
        queryKey: ["pruner", "instances", instanceId],
      });
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
      const genreTokens = [...genreSelection];
      const peopleTokens = scopeRow?.preview_include_people ?? [];
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
        setErr(
          "Each year must be a whole number between 1900 and 2100, or left empty.",
        );
        return;
      }
      if (yMin != null && yMax != null && yMin > yMax) {
        setErr("Minimum year must be less than or equal to maximum year.");
        return;
      }
      const collectionsPreserve =
        isPlex && props.scope === "movies"
          ? (scopeRow?.preview_include_collections ?? [])
          : [];
      const payload = {
        preview_include_genres: genreTokens,
        preview_include_people: peopleTokens,
        preview_year_min: yearMinStr.trim() ? yMin : null,
        preview_year_max: yearMaxStr.trim() ? yMax : null,
        preview_include_studios: studioTokens,
        ...(isPlex && props.scope === "movies"
          ? { preview_include_collections: collectionsPreserve }
          : {}),
        csrf_token,
      };
      await patchPrunerScope(instanceId, props.scope, payload);
      await qc.invalidateQueries({
        queryKey: ["pruner", "instances", instanceId],
      });
      setBundleMsg(
        props.scope === "tv" ? "Saved TV filters." : "Saved Movies filters.",
      );
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function saveProviderPeopleBundle() {
    setBundleMsg(null);
    setErr(null);
    setBusy(true);
    try {
      const csrf_token = await fetchCsrfToken();
      const lines = peopleText
        .split(/[\n,]+/)
        .map((s) => s.trim())
        .filter(Boolean);
      await patchPrunerScope(instanceId, props.scope, {
        preview_include_people: lines,
        preview_include_people_roles: isPlex
          ? peopleRolesForPlexPersist(peopleRoles)
          : [...peopleRoles],
        csrf_token,
      });
      await qc.invalidateQueries({
        queryKey: ["pruner", "instances", instanceId],
      });
      setBundleMsg(
        props.scope === "tv" ? "Saved TV people." : "Saved Movies people.",
      );
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return {
    props,
    instanceId,
    instance,
    fmt,
    isProvider,
    provSub,
    canOperate,
    showInteractiveControls,
    scopeRow,
    label,
    isPlex,
    libraryTabPhrase,
    previewRunsQueryKey,
    runsQuery,
    applyEligQuery,
    applySnapshotOperatorLabel,
    busy,
    setBusy,
    err,
    setErr,
    preview,
    setPreview,
    jsonPreview,
    setJsonPreview,
    schedEnabled,
    setSchedEnabled,
    schedIntervalSec,
    setSchedIntervalSec,
    schedIntervalMinDraft,
    setSchedIntervalMinDraft,
    schedHoursLimited,
    setSchedHoursLimited,
    schedDays,
    setSchedDays,
    schedStart,
    setSchedStart,
    schedEnd,
    setSchedEnd,
    schedMsg,
    setSchedMsg,
    applyModalRunId,
    setApplyModalRunId,
    applySnapshotConfirmed,
    setApplySnapshotConfirmed,
    staleNeverEnabled,
    setStaleNeverEnabled,
    staleNeverDays,
    setStaleNeverDays,
    staleNeverMsg,
    setStaleNeverMsg,
    watchedTvEnabled,
    setWatchedTvEnabled,
    watchedTvMsg,
    setWatchedTvMsg,
    watchedMoviesEnabled,
    setWatchedMoviesEnabled,
    watchedMoviesMsg,
    setWatchedMoviesMsg,
    lowRatingEnabled,
    setLowRatingEnabled,
    lowRatingMax,
    setLowRatingMax,
    lowRatingMsg,
    setLowRatingMsg,
    unwatchedStaleEnabled,
    setUnwatchedStaleEnabled,
    unwatchedStaleDays,
    setUnwatchedStaleDays,
    unwatchedStaleMsg,
    setUnwatchedStaleMsg,
    genreSelection,
    setGenreSelection,
    genreMsg,
    setGenreMsg,
    peopleText,
    setPeopleText,
    peopleRoles,
    setPeopleRoles,
    peopleMsg,
    setPeopleMsg,
    yearMinStr,
    setYearMinStr,
    yearMaxStr,
    setYearMaxStr,
    yearMsg,
    setYearMsg,
    studioText,
    setStudioText,
    studioMsg,
    setStudioMsg,
    collectionText,
    setCollectionText,
    collectionMsg,
    setCollectionMsg,
    previewMaxItems,
    setPreviewMaxItems,
    previewMaxItemsMsg,
    setPreviewMaxItemsMsg,
    bundleMsg,
    setBundleMsg,
    rulesTvOlderDaysStr,
    setRulesTvOlderDaysStr,
    rulesMoviesLowRatingStr,
    setRulesMoviesLowRatingStr,
    rulesMoviesUnwatchedDaysStr,
    setRulesMoviesUnwatchedDaysStr,
    ruleFamilyColumnLabel,
    saveSchedule,
    savePreviewMaxItemsSettings,
    saveStaleNeverSettings,
    saveGenreFilters,
    savePeopleFilters,
    savePreviewYearBounds,
    saveStudioPreviewFilters,
    saveCollectionPreviewFilters,
    saveWatchedMoviesSettings,
    saveLowRatingMovieSettings,
    saveUnwatchedStaleMovieSettings,
    saveWatchedTvSettings,
    runPreview,
    runStaleNeverPreview,
    runWatchedMoviesPreview,
    runLowRatingMoviesPreview,
    runUnwatchedStaleMoviesPreview,
    runWatchedTvPreview,
    openApplyModal,
    closeApplyModal,
    confirmApplyFromSnapshot,
    loadJsonFor,
    saveProviderTvRulesBundle,
    saveProviderMoviesRulesBundle,
    saveProviderFiltersBundle,
    saveProviderPeopleBundle,
  };
}
