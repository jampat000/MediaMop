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
import { MmOnOffSwitch } from "../../components/ui/mm-on-off-switch";
import {
  MM_SCHEDULE_TIME_WINDOW_HELPER,
  MmScheduleDayChips,
  MmScheduleTimeFields,
} from "../../components/ui/mm-schedule-window-controls";
import {
  committedPrunerRunIntervalMinutes,
  finalizePrunerRunIntervalMinutesDraft,
  PRUNER_RUN_INTERVAL_MAX_MINUTES,
  PRUNER_RUN_INTERVAL_MIN_MINUTES,
} from "../../lib/ui/pruner-schedule-interval";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import { PrunerGenreMultiSelect, prunerGenresFromApi } from "./pruner-genre-multi-select";
import {
  PrunerPeopleRoleCheckboxes,
  normalizePeopleRolesFromApi,
  peopleRolesForPlexPersist,
  peopleRolesForPlexUiState,
  type PrunerPeopleRoleId,
} from "./pruner-people-roles";
import { useAppDateFormatter } from "../../lib/ui/mm-format-date";
import { formatPrunerDateTime, previewRunRowCaption } from "./pruner-ui-utils";
import { PrunerProviderSection } from "./pruner-scope-tab-sections";

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
  /** When variant is provider, selects one subsection (Rules / Filters / People). */
  providerSubSection?: "rules" | "filters" | "people";
}) {
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
  const [schedIntervalMinDraft, setSchedIntervalMinDraft] = useState<string | null>(null);
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
  const [unwatchedStaleMsg, setUnwatchedStaleMsg] = useState<string | null>(null);
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
  const [previewMaxItemsMsg, setPreviewMaxItemsMsg] = useState<string | null>(null);
  const [bundleMsg, setBundleMsg] = useState<string | null>(null);
  /** Provider Rules: single inputs (0 = off) mapped to never-played / low-rating / unwatched stale. */
  const [rulesTvOlderDaysStr, setRulesTvOlderDaysStr] = useState("0");
  const [rulesMoviesLowRatingStr, setRulesMoviesLowRatingStr] = useState("0");
  const [rulesMoviesUnwatchedDaysStr, setRulesMoviesUnwatchedDaysStr] = useState("0");
  const isProvider = props.variant === "provider";
  const provSub = props.providerSubSection;
  const canOperate = me.data?.role === "admin" || me.data?.role === "operator";
  const showInteractiveControls = canOperate || Boolean(props.disabledMode);

  const scopeRow = instance?.scopes.find((s) => s.media_scope === props.scope);
  const label = props.scope === "tv" ? "TV shows" : "Movies";
  const isPlex = instance?.provider === "plex";
  const libraryTabPhrase = props.scope === "tv" ? "TV tab" : "Movies tab";

  function ruleFamilyColumnLabel(id: string): string {
    if (id === RULE_FAMILY_WATCHED_TV_REPORTED) return "Delete watched TV episodes";
    if (id === RULE_FAMILY_WATCHED_MOVIES_REPORTED) return "Delete watched movies";
    if (id === RULE_FAMILY_WATCHED_MOVIE_LOW_RATING_REPORTED) return "Delete watched movies below your score";
    if (id === RULE_FAMILY_UNWATCHED_MOVIE_STALE_REPORTED) return "Delete unwatched movies older than your age setting";
    if (id === RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED) return "Delete never-started TV or movies older than your age setting";
    if (id === RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED) return "Delete items missing a main poster or episode image";
    return "This cleanup type";
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
      isPlex ? peopleRolesForPlexUiState(scopeRow.preview_include_people_roles) : normalizePeopleRolesFromApi(scopeRow.preview_include_people_roles),
    );
    setYearMinStr(scopeRow.preview_year_min != null ? String(scopeRow.preview_year_min) : "");
    setYearMaxStr(scopeRow.preview_year_max != null ? String(scopeRow.preview_year_max) : "");
    setStudioText((scopeRow.preview_include_studios ?? []).join(", "));
    setCollectionText((scopeRow.preview_include_collections ?? []).join(", "));
    setPreviewMaxItems(scopeRow.preview_max_items);
    if (props.scope === "tv") {
      setRulesTvOlderDaysStr(
        !scopeRow.never_played_stale_reported_enabled ? "0" : String(scopeRow.never_played_min_age_days),
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
        !scopeRow.unwatched_movie_stale_reported_enabled ? "0" : String(scopeRow.unwatched_movie_stale_min_age_days),
      );
    }
  }, [
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
          ? finalizePrunerRunIntervalMinutesDraft(schedIntervalMinDraft, schedIntervalSec)
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
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      setSchedMsg(`Saved. Automatic scans use this server’s ${libraryTabPhrase} only.`);
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
      setPreviewMaxItemsMsg("Saved how many items each scan may check on this tab.");
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
      setStaleNeverMsg("Saved never-watched TV and movie age settings for this tab.");
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
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      setGenreMsg(
        tokens.length
          ? "Saved your genre picks for this tab."
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
        preview_include_people_roles: isPlex ? peopleRolesForPlexPersist(peopleRoles) : [...peopleRoles],
        csrf_token,
      });
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      setPeopleMsg(
        tokens.length
          ? "Saved name filters for this tab."
          : "Cleared name filters for this tab.",
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
      setYearMsg("Saved release year limits for this tab.");
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
          ? "Saved studio filters for this tab."
          : "Cleared studio filters for this tab.",
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
          ? "Saved collection filters for this tab."
          : "Cleared collection filters for this tab.",
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
      setWatchedMoviesMsg("Saved watched-movie cleanup setting for this tab.");
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
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
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
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      setWatchedTvMsg("Saved watched-TV cleanup setting for this tab.");
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
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      await qc.invalidateQueries({ queryKey: previewRunsQueryKey });
      setPreview("Scan for broken posters and images started. The table below updates when results are ready.");
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
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      await qc.invalidateQueries({ queryKey: previewRunsQueryKey });
      setPreview("Scan for unwatched TV or movies older than your setting started. The table below updates when ready.");
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
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      await qc.invalidateQueries({ queryKey: previewRunsQueryKey });
      setPreview("Scan for watched movies started. The table below updates when ready.");
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
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      await qc.invalidateQueries({ queryKey: previewRunsQueryKey });
      setPreview("Scan for low-score watched movies started. The table below updates when ready.");
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
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      await qc.invalidateQueries({ queryKey: previewRunsQueryKey });
      setPreview("Scan for old unwatched movies started. The table below updates when ready.");
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
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      await qc.invalidateQueries({ queryKey: previewRunsQueryKey });
      setPreview("Scan for watched TV shows started. The table below updates when ready.");
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
      await postPrunerApplyFromPreview(instanceId, props.scope, runId);
      await qc.invalidateQueries({ queryKey: previewRunsQueryKey });
      await qc.invalidateQueries({ queryKey: ["activity"] });
      closeApplyModal();
      setPreview(`Deletion started (${opLabel}). Check Activity for removed, skipped, and failed counts.`);
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
          : { watched_movie_low_rating_max_jellyfin_emby_community_rating: cap }),
        unwatched_movie_stale_reported_enabled: uwOn,
        unwatched_movie_stale_min_age_days: uwDays,
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
        setErr("Each year must be a whole number between 1900 and 2100, or left empty.");
        return;
      }
      if (yMin != null && yMax != null && yMin > yMax) {
        setErr("Minimum year must be less than or equal to maximum year.");
        return;
      }
      const collectionsPreserve = isPlex && props.scope === "movies" ? (scopeRow?.preview_include_collections ?? []) : [];
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
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      setBundleMsg(props.scope === "tv" ? "Saved TV filters." : "Saved Movies filters.");
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
        preview_include_people_roles: isPlex ? peopleRolesForPlexPersist(peopleRoles) : [...peopleRoles],
        csrf_token,
      });
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      setBundleMsg(props.scope === "tv" ? "Saved TV people." : "Saved Movies people.");
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
          <div className="mm-bubble-stack" data-testid="pruner-provider-plex-tv-unsupported-rules">
            <div className="space-y-1.5">
              <p className="text-sm font-medium text-[var(--mm-text1)]">Watched TV removal</p>
              <p className="text-xs leading-relaxed text-[var(--mm-text3)]">Not supported for Plex.</p>
            </div>
            <div className="space-y-1.5">
              <p className="text-sm font-medium text-[var(--mm-text1)]">Unwatched TV older than N days</p>
              <p className="text-xs leading-relaxed text-[var(--mm-text3)]">Not supported for Plex.</p>
            </div>
          </div>
        );
      }
      return (
        <div className="mm-bubble-stack">
          <div data-testid="pruner-watched-tv-panel">
            {showInteractiveControls ? (
              <MmOnOffSwitch
                id={`pruner-provider-tv-watched-${instanceId}`}
                label="Watched TV removal"
                enabled={watchedTvEnabled}
                disabled={busy}
                onChange={setWatchedTvEnabled}
              />
            ) : (
              <p className="text-xs text-[var(--mm-text2)]">
                Watched TV removal: <strong>{scopeRow?.watched_tv_reported_enabled ? "On" : "Off"}</strong>
              </p>
            )}
            <p className="mt-2 text-xs leading-relaxed text-[var(--mm-text3)]">
              Delete items marked watched for this provider user.
            </p>
          </div>
          <div data-testid="pruner-never-played-stale-panel">
            <p className="text-sm font-medium text-[var(--mm-text1)]">Unwatched TV older than N days</p>
            {showInteractiveControls ? (
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <input
                  type="number"
                  min={0}
                  max={3650}
                  className="mm-input w-24"
                  value={rulesTvOlderDaysStr}
                  disabled={busy}
                  onChange={(e) => setRulesTvOlderDaysStr(e.target.value)}
                />
                <span className="text-sm text-[var(--mm-text2)]">days</span>
              </div>
            ) : (
              <p className="mt-2 text-xs text-[var(--mm-text2)]">
                Days:{" "}
                <strong>
                  {!scopeRow?.never_played_stale_reported_enabled ? "0 (off)" : scopeRow.never_played_min_age_days}
                </strong>
              </p>
            )}
            <p className="mt-1 text-xs leading-relaxed text-[var(--mm-text3)]">
              Set 0 to disable. Minimum 7 days when active.
            </p>
          </div>
        </div>
      );
    }
    return (
      <div className="mm-bubble-stack">
        <div data-testid="pruner-watched-movies-panel">
          {showInteractiveControls ? (
            <MmOnOffSwitch
              id={`pruner-provider-movies-watched-${instanceId}`}
              label="Watched movies removal"
              enabled={watchedMoviesEnabled}
              disabled={busy}
              onChange={setWatchedMoviesEnabled}
            />
          ) : (
            <p className="text-xs text-[var(--mm-text2)]">
              Watched movies removal: <strong>{scopeRow?.watched_movies_reported_enabled ? "On" : "Off"}</strong>
            </p>
          )}
          <p className="mt-2 text-xs leading-relaxed text-[var(--mm-text3)]">
            {isPlex ? "Uses Plex watched state from allLeaves." : "Uses provider watched state for movie items."}
          </p>
        </div>
        <div data-testid="pruner-watched-low-rating-panel">
          <p className="text-sm font-medium text-[var(--mm-text1)]">Low-rating watched movies</p>
          <p className="mt-1 text-xs text-[var(--mm-text3)]">
            {isPlex ? "Plex audienceRating max (0–10)" : "Jellyfin/Emby CommunityRating max (0–10)"}
          </p>
          {showInteractiveControls ? (
            <input
              type="number"
              min={0}
              max={10}
              step="0.1"
              className="mm-input mt-2 w-28"
              value={rulesMoviesLowRatingStr}
              disabled={busy}
              onChange={(e) => setRulesMoviesLowRatingStr(e.target.value)}
            />
          ) : (
            <p className="mt-2 text-xs text-[var(--mm-text2)]">
              Max rating / off:{" "}
              <strong>
                {!scopeRow?.watched_movie_low_rating_reported_enabled
                  ? "0 (off)"
                  : isPlex
                    ? scopeRow.watched_movie_low_rating_max_plex_audience_rating
                    : scopeRow.watched_movie_low_rating_max_jellyfin_emby_community_rating}
              </strong>
            </p>
          )}
          <p className="mt-1 text-xs leading-relaxed text-[var(--mm-text3)]">Set 0 to disable.</p>
        </div>
        <div data-testid="pruner-unwatched-stale-panel">
          <p className="text-sm font-medium text-[var(--mm-text1)]">Unwatched movies older than N days</p>
          {showInteractiveControls ? (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <input
                type="number"
                min={0}
                max={3650}
                className="mm-input w-24"
                value={rulesMoviesUnwatchedDaysStr}
                disabled={busy}
                onChange={(e) => setRulesMoviesUnwatchedDaysStr(e.target.value)}
              />
              <span className="text-sm text-[var(--mm-text2)]">days</span>
            </div>
          ) : (
            <p className="mt-2 text-xs text-[var(--mm-text2)]">
              Days:{" "}
              <strong>
                {!scopeRow?.unwatched_movie_stale_reported_enabled ? "0 (off)" : scopeRow.unwatched_movie_stale_min_age_days}
              </strong>
            </p>
          )}
          <p className="mt-1 text-xs leading-relaxed text-[var(--mm-text3)]">Set 0 to disable.</p>
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
      <div className="mm-bubble-stack">
        {isPlex && props.scope === "tv" ? (
          <p className="text-xs leading-relaxed text-amber-100/90" data-testid="pruner-plex-tv-filters-scope-note" role="status">
            On Plex, filters apply to the missing primary art rule only.
          </p>
        ) : null}
        <div className="space-y-2" data-testid="pruner-genre-filters-panel">
          <p className="text-sm font-medium text-[var(--mm-text1)]">Genres</p>
          {showInteractiveControls ? (
            <PrunerGenreMultiSelect
              value={genreSelection}
              onChange={setGenreSelection}
              disabled={busy}
              testId={`pruner-genre-multiselect-provider-${instanceId}-${props.scope}`}
              filterHelperText=""
            />
          ) : (
            <p className="text-xs text-[var(--mm-text2)]">
              {(scopeRow?.preview_include_genres ?? []).join(", ") || "—"}
            </p>
          )}
          <p className="text-xs text-[var(--mm-text3)]">Leave none selected to include every genre.</p>
        </div>
        <div className="space-y-2" data-testid="pruner-year-filters-panel">
          <p className="text-sm font-medium text-[var(--mm-text1)]">Year range</p>
          {showInteractiveControls ? (
            <div className="flex flex-wrap items-end gap-3">
              <label className="text-sm text-[var(--mm-text2)]">
                Min year
                <input
                  type="number"
                  min={1900}
                  max={2100}
                  className="mm-input ml-2 mt-1 w-24"
                  placeholder="Min"
                  value={yearMinStr}
                  disabled={busy}
                  onChange={(e) => setYearMinStr(e.target.value)}
                />
              </label>
              <label className="text-sm text-[var(--mm-text2)]">
                Max year
                <input
                  type="number"
                  min={1900}
                  max={2100}
                  className="mm-input ml-2 mt-1 w-24"
                  placeholder="Max"
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
          <p className="text-xs text-[var(--mm-text3)]">Leave blank for open-ended. Range 1900–2100.</p>
        </div>
        <div className="space-y-2" data-testid="pruner-studio-preview-panel">
          <p className="text-sm font-medium text-[var(--mm-text1)]">Studio</p>
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
              {(scopeRow?.preview_include_studios ?? []).join(", ") || "—"}
            </p>
          )}
          <p className="text-xs text-[var(--mm-text3)]">Leave blank to include all studios.</p>
        </div>
      </div>
    );
  }

  function renderProviderPeopleControls(): ReactNode {
    return (
      <div className="space-y-3">
        <label className="block text-sm font-medium text-[var(--mm-text1)]" htmlFor={`pruner-people-names-${props.scope}-${instanceId}`}>
          Names
        </label>
        {showInteractiveControls ? (
          <textarea
            id={`pruner-people-names-${props.scope}-${instanceId}`}
            rows={5}
            className="mm-input min-h-[7rem] w-full resize-y font-sans text-sm"
            placeholder="e.g. Alex Carter, Jordan Lee (comma or one per line)"
            value={peopleText}
            disabled={busy}
            onChange={(e) => setPeopleText(e.target.value)}
          />
        ) : (
          <p className="whitespace-pre-wrap text-xs text-[var(--mm-text2)]">
            {(scopeRow?.preview_include_people ?? []).join("\n") || "—"}
          </p>
        )}
        <p className="text-xs text-[var(--mm-text3)]">Leave blank to use no name filter.</p>
        {showInteractiveControls ? (
          <PrunerPeopleRoleCheckboxes
            value={peopleRoles}
            onChange={setPeopleRoles}
            disabled={busy}
            variant={isPlex ? "plex" : "emby-jellyfin"}
            testId={`pruner-provider-inline-people-roles-${instanceId}-${props.scope}`}
          />
        ) : (
          <p className="text-xs text-[var(--mm-text2)]">
            Roles:{" "}
            <strong>
              {(scopeRow?.preview_include_people_roles ?? []).length
                ? (scopeRow?.preview_include_people_roles ?? []).join(", ")
                : "all credits"}
            </strong>
          </p>
        )}
      </div>
    );
  }

  if (isProvider && provSub === "rules") {
    const saveLabel = props.scope === "tv" ? "Save TV rules" : "Save Movies rules";
    const onSave = props.scope === "tv" ? saveProviderTvRulesBundle : saveProviderMoviesRulesBundle;
    const saveDisabled = busy || !showInteractiveControls || (isPlex && props.scope === "tv");
    return (
      <PrunerProviderSection scope={props.scope} section="rules">
        <fieldset disabled={Boolean(props.disabledMode)} className="flex min-h-0 flex-1 flex-col">
          <div className="mm-card-action-body min-h-0 flex-1">{renderProviderRulesControls()}</div>
          {showInteractiveControls ? (
            <div className="mm-card-action-footer">
              <button
                type="button"
                className={mmActionButtonClass({ variant: "primary", disabled: saveDisabled })}
                disabled={saveDisabled}
                onClick={() => void onSave()}
              >
                {busy ? "Saving…" : saveLabel}
              </button>
              {bundleMsg ? <p className="text-sm text-green-600">{bundleMsg}</p> : null}
              {err ? (
                <p className="text-sm text-red-600" role="alert">
                  {err}
                </p>
              ) : null}
            </div>
          ) : (
            <>
              {bundleMsg ? <p className="mt-3 text-sm text-green-600">{bundleMsg}</p> : null}
              {err ? (
                <p className="mt-2 text-sm text-red-600" role="alert">
                  {err}
                </p>
              ) : null}
            </>
          )}
        </fieldset>
      </PrunerProviderSection>
    );
  }

  if (isProvider && provSub === "filters") {
    const saveLabel = props.scope === "tv" ? "Save TV filters" : "Save Movies filters";
    return (
      <PrunerProviderSection scope={props.scope} section="filters">
        <fieldset disabled={Boolean(props.disabledMode)} className="flex min-h-0 flex-1 flex-col">
          <div className="mm-card-action-body min-h-0 flex-1">{renderProviderFiltersControls()}</div>
          {showInteractiveControls ? (
            <div className="mm-card-action-footer">
              <button
                type="button"
                className={mmActionButtonClass({ variant: "primary", disabled: busy })}
                disabled={busy}
                onClick={() => void saveProviderFiltersBundle()}
              >
                {busy ? "Saving…" : saveLabel}
              </button>
              {bundleMsg ? <p className="text-sm text-green-600">{bundleMsg}</p> : null}
              {err ? (
                <p className="text-sm text-red-600" role="alert">
                  {err}
                </p>
              ) : null}
            </div>
          ) : (
            <>
              {bundleMsg ? <p className="mt-3 text-sm text-green-600">{bundleMsg}</p> : null}
              {err ? (
                <p className="mt-2 text-sm text-red-600" role="alert">
                  {err}
                </p>
              ) : null}
            </>
          )}
        </fieldset>
      </PrunerProviderSection>
    );
  }

  if (isProvider && provSub === "people") {
    const saveLabel = props.scope === "tv" ? "Save TV people" : "Save Movies people";
    return (
      <PrunerProviderSection scope={props.scope} section="people">
        <fieldset disabled={Boolean(props.disabledMode)} className="flex min-h-0 flex-1 flex-col">
          <div className="mm-card-action-body min-h-0 flex-1">{renderProviderPeopleControls()}</div>
          {showInteractiveControls ? (
            <div className="mm-card-action-footer">
              <button
                type="button"
                className={mmActionButtonClass({ variant: "primary", disabled: busy })}
                disabled={busy}
                onClick={() => void saveProviderPeopleBundle()}
              >
                {busy ? "Saving…" : saveLabel}
              </button>
              {bundleMsg ? <p className="text-sm text-green-600">{bundleMsg}</p> : null}
              {err ? (
                <p className="text-sm text-red-600" role="alert">
                  {err}
                </p>
              ) : null}
            </div>
          ) : (
            <>
              {bundleMsg ? <p className="mt-3 text-sm text-green-600">{bundleMsg}</p> : null}
              {err ? (
                <p className="mt-2 text-sm text-red-600" role="alert">
                  {err}
                </p>
              ) : null}
            </>
          )}
        </fieldset>
      </PrunerProviderSection>
    );
  }

  if (isProvider && !provSub) {
    return (
        <p className="text-sm text-red-600" role="alert" data-testid="pruner-provider-subsection-missing">
        Something is misconfigured. Try reloading the page or opening the provider tab again.
      </p>
    );
  }

  return (
    <section
      className={isProvider ? "mm-bubble-stack w-full min-w-0" : "mm-bubble-stack max-w-3xl"}
      aria-labelledby="pruner-scope-heading"
    >
      <fieldset disabled={Boolean(props.disabledMode)} className="mm-bubble-stack">
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
          Save this server on the Connection tab first to turn on these controls.
        </p>
      ) : null}
      <div
        className="space-y-2 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
        data-testid="pruner-run-limits-panel"
      >
        <p className="text-sm font-semibold text-[var(--mm-text)]">How many items each scan may check</p>
        <p className="text-xs text-[var(--mm-text2)]" data-testid="pruner-delete-cap-note">
          This limit only affects how many rows MediaMop lists for you to review. Deleting still uses exactly the list you
          confirmed, not a fresh scan.
        </p>
        {showInteractiveControls ? (
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-xs text-[var(--mm-text2)]">
              Max items per scan (1–5000)
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
            Max items per scan: <strong>{scopeRow?.preview_max_items ?? "—"}</strong>. Sign in as an operator to edit.
          </p>
        )}
      </div>
      <div
        className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-surface2)]/40 px-4 py-3 text-xs text-[var(--mm-text2)] sm:text-sm"
        data-testid="pruner-scope-trust-banner"
      >
        <p>Each scan saves a fixed list you can review. Deleting uses only that saved list, not a new pass over the library.</p>
      </div>
      {!isProvider && !isPlex ? (
        <p className="text-sm text-[var(--mm-text2)]">
          {props.scope === "tv"
            ? "Scans can list episodes missing a main image, or episodes never played for your MediaMop user that are older than the age you set. Each cleanup type has its own button above."
            : "Scans can list movies missing a main poster, movies marked watched for your MediaMop user, or movies never watched and older than the age you set. Each cleanup type has its own button above."}
        </p>
      ) : !isProvider ? (
        <p className="text-sm text-[var(--mm-text2)]">
          On Plex, scans read the same on-server details as Jellyfin and Emby: broken posters look for missing episode or
          movie art. Movie scans can also find watched titles, low audience scores, and old unwatched titles. Deleting
          only touches the exact titles from the list you reviewed; items already gone are counted as skipped. Whether
          Plex removes files or only metadata depends on your Plex server.
        </p>
      ) : null}
      {isProvider ? (
        <p className="text-xs text-[var(--mm-text2)]">
          Run a scan, review the list or raw details, then delete from that list if you choose.
        </p>
      ) : null}
      {isPlex && scopeRow && !isProvider ? (
        <p className="text-xs text-[var(--mm-text2)]" data-testid="pruner-plex-preview-cap-note">
          Plex stops each scan at the smaller of your per-tab item limit and a built-in safety cap. If a scan says the
          list was shortened, there were more matches than MediaMop showed this time.
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
          Optional filters for scans
        </h3>
        <p className="text-xs text-[var(--mm-text2)]">
          Filters affect scan results on this {libraryTabPhrase} only.
        </p>
        {isPlex && props.scope === "tv" && isProvider ? (
          <p className="mt-1 text-xs text-amber-100/90" data-testid="pruner-plex-tv-filters-scope-note" role="status">
            On Plex TV, genre, people, year, and studio filters only affect scans for broken posters and images.
          </p>
        ) : null}
      </div>
      {scopeRow ? (
        <div className="space-y-2 text-sm text-[var(--mm-text)]" data-testid="pruner-genre-filters-panel">
          <p className="text-sm font-semibold text-[var(--mm-text)]">
            Optional genres (this {libraryTabPhrase} only)
          </p>
          <p className="text-xs text-[var(--mm-text2)]">Pick from the list below; leave none selected to include every genre.</p>
          {isPlex && !isProvider ? (
            <p
              className="text-xs text-amber-100/90"
              data-testid="pruner-plex-genre-empty-preview-note"
            >
              If a scan finishes with <strong>nothing listed</strong> while genres are selected, nothing in this pass
              matched both the rule and those genres — it does not prove your library is already clean.
            </p>
          ) : null}
          {showInteractiveControls ? (
            <div className="space-y-2">
              <PrunerGenreMultiSelect
                value={genreSelection}
                onChange={setGenreSelection}
                disabled={busy}
                testId={`pruner-genre-multiselect-${instanceId}-${props.scope}`}
                filterHelperText=""
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
        <div className="space-y-2 text-sm text-[var(--mm-text)]" data-testid="pruner-people-filters-panel">
          <p className="text-sm font-semibold text-[var(--mm-text)]">
            Optional cast and crew names (this {libraryTabPhrase} only)
          </p>
          <p className="text-xs text-[var(--mm-text2)]">Comma-separated full names.</p>
          {isPlex && props.scope === "tv" && isProvider ? null : isPlex && !isProvider ? (
            <p className="text-xs text-[var(--mm-text2)]" data-testid="pruner-people-plex-note">
              Plex: names apply to broken-poster scans plus the movie scans above. They come from cast, writer, and
              director lines on each title.
            </p>
          ) : !isProvider ? (
            <p className="text-xs text-[var(--mm-text2)]" data-testid="pruner-people-jf-emby-note">
              Jellyfin / Emby: names come from each item’s People list on the server and apply to every scan on this tab.
            </p>
          ) : null}
          {showInteractiveControls ? (
            <div className="space-y-3">
              <textarea
                rows={5}
                className="mm-input min-h-[7rem] w-full resize-y font-sans text-sm"
                placeholder="e.g. Alex Carter, Jordan Lee (comma or one per line)"
                value={peopleText}
                disabled={busy}
                onChange={(e) => setPeopleText(e.target.value)}
              />
              <p className="text-xs text-[var(--mm-text3)]">Leave blank to use no name filter.</p>
              <PrunerPeopleRoleCheckboxes
                value={peopleRoles}
                onChange={setPeopleRoles}
                disabled={busy}
                variant={isPlex ? "plex" : "emby-jellyfin"}
                testId={`pruner-people-filters-roles-${instanceId}-${props.scope}`}
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
          <p className="text-sm font-semibold text-[var(--mm-text)]">Optional release years (this {libraryTabPhrase} only)</p>
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
          <p className="text-sm font-semibold text-[var(--mm-text)]">Optional studios (this {libraryTabPhrase} only)</p>
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
          <p className="text-sm font-semibold text-[var(--mm-text)]">Optional Plex movie collections</p>
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
              ? "Plex does not support watched-TV or never-started cleanup on the Movies tab."
              : "Plex does not support watched-TV or never-started TV cleanup on the TV tab."}
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
              ? "Delete TV shows not watched in the last N days — Jellyfin / Emby"
              : "Delete TV or movies never started and older than N days — Jellyfin / Emby"}
          </p>
          <p className="text-xs text-[var(--mm-text2)]">Only titles with no play time and older than this age.</p>
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
                  ? "Turn on never-watched TV older than this age"
                  : "Turn on never-watched TV or movies older than this age"}
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
                  Save never-watched age rule
                </button>
              </div>
              {staleNeverMsg ? <p className="text-xs text-green-600">{staleNeverMsg}</p> : null}
              <button
                type="button"
                className="rounded-md bg-[var(--mm-surface2)] px-3 py-1.5 text-sm font-medium text-[var(--mm-text)] ring-1 ring-[var(--mm-border)] disabled:opacity-50"
                disabled={busy || !staleNeverEnabled}
                title={!staleNeverEnabled ? "Turn the rule on and save before running this scan." : undefined}
                onClick={() => void runStaleNeverPreview()}
              >
                {props.scope === "tv"
                  ? "Scan for unwatched TV shows older than your setting"
                  : "Scan for unwatched TV or movies older than your setting"}
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
            <p className="text-sm font-semibold text-[var(--mm-text)]">Delete watched TV episodes — Jellyfin / Emby</p>
            <p className="text-xs text-[var(--mm-text2)]">Uses the watched flag for your MediaMop user on this server.</p>
            {showInteractiveControls ? (
              <div className="space-y-2">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={watchedTvEnabled}
                    disabled={busy}
                    onChange={(e) => setWatchedTvEnabled(e.target.checked)}
                  />
                  Turn on watched-TV cleanup
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
                  title={!watchedTvEnabled ? "Turn the rule on and save before running this scan." : undefined}
                  onClick={() => void runWatchedTvPreview()}
                >
                  Scan for watched TV shows
                </button>
              </div>
            ) : (
              <p className="text-xs text-[var(--mm-text2)]">
                Watched TV rule is <strong>{scopeRow?.watched_tv_reported_enabled ? "on" : "off"}</strong> for this{" "}
                {libraryTabPhrase}.
                Sign in as an operator to change it.
              </p>
            )}
          </div>
        ) : null}
        </Fragment>
      ) : null}
      {!isPlex ? null : props.scope === "movies" && !isProvider ? (
        <p className="text-xs text-[var(--mm-text2)]">
          On Plex, watched movies, low-score movies, and old unwatched movies all use the same on-server details MediaMop
          already reads for other scans — watched means the server shows you played it; low score uses Plex audience
          rating; old unwatched uses when Plex says the title was added to the library.
        </p>
      ) : null}
      <div>
        <h3 className="text-base font-semibold text-[var(--mm-text)]" data-testid="pruner-rules-section-heading">
          Cleanup rules
        </h3>
        <p className="text-xs text-[var(--mm-text2)]">Turn a rule on, save, then run its scan when you are ready.</p>
      </div>
      {props.scope === "movies" ? (
          <>
            <div
              className="space-y-2 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
              data-testid="pruner-watched-movies-panel"
            >
              <p className="text-sm font-semibold text-[var(--mm-text)]">
                {isPlex ? "Delete watched movies — Plex" : "Delete watched movies — Jellyfin / Emby"}
              </p>
              <p className="text-xs text-[var(--mm-text2)]">
                {isPlex ? "Uses Plex watched flags for your MediaMop user." : "Uses the server watched flag for each movie."}
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
                    Turn on watched-movie cleanup
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
                      !watchedMoviesEnabled ? "Turn the rule on and save before running this scan." : undefined
                    }
                    onClick={() => void runWatchedMoviesPreview()}
                  >
                    Scan for watched movies
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
                {isPlex ? "Delete low-score watched movies — Plex" : "Delete low-score watched movies — Jellyfin / Emby"}
              </p>
              <p className="text-xs text-[var(--mm-text2)]">
                {isPlex ? "Uses Plex audience rating." : "Uses your server’s community rating."}
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
                    Turn on low-score watched-movie cleanup
                  </label>
                  <label className="flex flex-wrap items-center gap-2 text-sm text-[var(--mm-text2)]">
                    {isPlex
                      ? "Highest Plex audience rating to keep (0–10)"
                      : "Highest community rating to keep (0–10)"}
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
                      !lowRatingEnabled ? "Turn the rule on and save before running this scan." : undefined
                    }
                    onClick={() => void runLowRatingMoviesPreview()}
                  >
                    Scan for low-score watched movies
                  </button>
                </div>
              ) : (
                <p className="text-xs text-[var(--mm-text2)]">
                  Low-score rule is <strong>{scopeRow?.watched_movie_low_rating_reported_enabled ? "on" : "off"}</strong>
                  {scopeRow?.watched_movie_low_rating_reported_enabled ? (
                    <>
                      {" "}
                      (delete watched movies rated below{" "}
                      {isPlex
                        ? scopeRow.watched_movie_low_rating_max_plex_audience_rating
                        : scopeRow.watched_movie_low_rating_max_jellyfin_emby_community_rating}
                      ).
                    </>
                  ) : null}{" "}
                  Sign in as an operator to change it.
                </p>
              )}
            </div>
            <div
              className="space-y-2 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
              data-testid="pruner-unwatched-stale-panel"
            >
              <p className="text-sm font-semibold text-[var(--mm-text)]">
                {isPlex ? "Delete old unwatched movies — Plex" : "Delete old unwatched movies — Jellyfin / Emby"}
              </p>
              <p className="text-xs text-[var(--mm-text2)]">
                {isPlex ? "Never watched, using when Plex added the title." : "Never watched, using when the server created the title."}
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
                    Turn on old unwatched movie cleanup
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
                      !unwatchedStaleEnabled ? "Turn the rule on and save before running this scan." : undefined
                    }
                    onClick={() => void runUnwatchedStaleMoviesPreview()}
                  >
                    Scan for old unwatched movies
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
          <h3 className="text-sm font-semibold text-[var(--mm-text)]">Latest automatic scan (this {libraryTabPhrase})</h3>
          <p className="mt-1 text-xs text-[var(--mm-text2)]">
            Quick readout from the last finished scan — use the history table for older runs.
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
              <dt className="inline text-[var(--mm-text3)]">Items matched</dt>{" "}
              <dd className="inline font-medium text-[var(--mm-text1)]">{scopeRow.last_preview_candidate_count ?? "—"}</dd>
            </div>
            <div>
              <dt className="inline text-[var(--mm-text3)]">Problem detail</dt>{" "}
              <dd className="inline text-[var(--mm-text1)]">{scopeRow.last_preview_error ?? "—"}</dd>
            </div>
          </dl>
        </div>
      ) : null}
      <div>
        <h3 className="text-base font-semibold text-[var(--mm-text)]" data-testid="pruner-actions-history-heading">
          {isProvider ? "Scan actions" : "Scan and delete actions"}
        </h3>
        {isProvider ? null : (
          <p className="text-xs text-[var(--mm-text2)]">
            Run scans, review the table, then delete from one chosen list if you want. The table explains empty results and
            types your server does not support.
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
            Scan for broken posters
          </button>
          <button
            type="button"
            className="rounded-md border border-[var(--mm-border)] px-3 py-1.5 text-sm font-medium text-[var(--mm-text)] disabled:opacity-50"
            disabled={busy || !scopeRow?.last_preview_run_uuid}
            onClick={() => void loadJsonFor(scopeRow?.last_preview_run_uuid)}
          >
            View last scan results
          </button>
          {isProvider && scopeRow?.last_preview_run_uuid ? (
            <button
              type="button"
              className="rounded-md border border-red-900/50 bg-red-950/30 px-3 py-1.5 text-sm font-medium text-red-100 disabled:opacity-50"
              disabled={busy}
              onClick={() => openApplyModal(scopeRow.last_preview_run_uuid!)}
            >
              Delete from last scan
            </button>
          ) : null}
        </div>
      ) : (
        <p className="text-sm text-[var(--mm-text2)]">Sign in as an operator to run scans.</p>
      )}
      <div className="mm-card mm-dash-card flex min-h-0 flex-col p-6" data-testid="pruner-scope-scheduled-preview">
        <div className="mm-card-action-body flex-1 min-h-0">
          <div>
            <h3 className="text-base font-semibold text-[var(--mm-text1)]">
              Automatic scans ({props.scope === "tv" ? "TV shows" : "Movies"})
            </h3>
            <p className="mt-1 text-sm text-[var(--mm-text2)]">
              The schedule runs your saved criteria automatically and records a review snapshot. Deleting only happens when
              automatic apply is enabled for this library and uses that saved snapshot.
            </p>
          </div>
          {showInteractiveControls ? (
            <>
              <MmOnOffSwitch
                id={`pruner-scope-${instanceId}-${props.scope}-timed`}
                label="Enable timed scans"
                enabled={schedEnabled}
                disabled={busy}
                onChange={setSchedEnabled}
              />
              <div>
                <span className="text-sm font-medium text-[var(--mm-text1)]">Run interval (minutes)</span>
                <p className="mt-1 text-xs text-[var(--mm-text3)]">How often this search runs automatically.</p>
                <input
                  type="number"
                  min={PRUNER_RUN_INTERVAL_MIN_MINUTES}
                  max={PRUNER_RUN_INTERVAL_MAX_MINUTES}
                  className="mm-input mt-2 w-full"
                  value={
                    schedIntervalMinDraft !== null
                      ? schedIntervalMinDraft
                      : committedPrunerRunIntervalMinutes(schedIntervalSec)
                  }
                  onFocus={() => setSchedIntervalMinDraft(committedPrunerRunIntervalMinutes(schedIntervalSec))}
                  onChange={(e) => setSchedIntervalMinDraft(e.target.value)}
                  onBlur={() => setSchedIntervalMinDraft(null)}
                  disabled={busy}
                  aria-label="Run interval in minutes"
                />
              </div>
              <div className="space-y-3">
                <div>
                  <span className="text-sm font-medium text-[var(--mm-text1)]">Schedule window</span>
                  <p className="mt-1 text-xs text-[var(--mm-text3)]">{MM_SCHEDULE_TIME_WINDOW_HELPER}</p>
                </div>
                <div className="space-y-4">
                  <MmOnOffSwitch
                    id={`pruner-scope-${instanceId}-${props.scope}-hours`}
                    label="Limit to these hours"
                    enabled={schedHoursLimited}
                    disabled={busy}
                    onChange={setSchedHoursLimited}
                  />
                  <div className="space-y-2">
                    <span className="text-sm font-medium text-[var(--mm-text1)]">Days</span>
                    <MmScheduleDayChips scheduleDaysCsv={schedDays} disabled={busy} onChangeCsv={setSchedDays} />
                  </div>
                  <MmScheduleTimeFields
                    idPrefix={`pruner-scope-${instanceId}-${props.scope}`}
                    start={schedStart}
                    end={schedEnd}
                    disabled={busy}
                    onStart={setSchedStart}
                    onEnd={setSchedEnd}
                  />
                </div>
              </div>
            </>
          ) : (
            <p className="text-sm text-[var(--mm-text2)]">
              Timed scans are <strong>{scopeRow?.scheduled_preview_enabled ? "on" : "off"}</strong>
              {scopeRow ? (
                <>
                  {" "}
                  (every {Math.round(scopeRow.scheduled_preview_interval_seconds / 60)} minutes). Sign in
                  as an operator to change it.
                </>
              ) : null}
            </p>
          )}
          <p className="text-xs text-[var(--mm-text3)]">
            Last automatic scan:{" "}
            <span className="font-medium text-[var(--mm-text1)]">
              {scopeRow?.last_scheduled_preview_enqueued_at ? fmt(scopeRow.last_scheduled_preview_enqueued_at) : "Never run"}
            </span>
          </p>
        </div>
        {showInteractiveControls ? (
          <div className="mm-card-action-footer">
            <button
              type="button"
              className={`${mmActionButtonClass({ variant: "primary", disabled: busy })} w-full`}
              disabled={busy}
              onClick={() => void saveSchedule()}
            >
              {props.scope === "tv" ? "Save TV schedule window" : "Save Movies schedule window"}
            </button>
            {schedMsg ? <p className="text-xs text-green-600">{schedMsg}</p> : null}
          </div>
        ) : null}
      </div>
      {!isProvider ? (
      <div className="space-y-2" data-testid="pruner-preview-runs-history">
        <h3 className="text-sm font-semibold text-[var(--mm-text)]">
          Recent scans ({props.scope === "tv" ? "TV shows" : "Movies"})
        </h3>
        {runsQuery.isLoading ? (
          <p className="text-sm text-[var(--mm-text2)]">Loading history…</p>
        ) : runsQuery.isError ? (
          <p className="text-sm text-red-600" role="alert">
            {(runsQuery.error as Error).message}
          </p>
        ) : runsQuery.data?.length ? (
          <div className="overflow-x-auto rounded-md border border-[var(--mm-border)]">
            <table className="w-full min-w-[30rem] border-collapse text-left text-sm text-[var(--mm-text)]">
              <thead className="border-b border-[var(--mm-border)] bg-[var(--mm-surface2)] text-xs uppercase text-[var(--mm-text2)]">
                <tr>
                  <th className="px-2 py-2">#</th>
                  <th className="px-2 py-2">Cleanup type</th>
                  <th className="px-2 py-2">When</th>
                  <th className="px-2 py-2">Result</th>
                  <th className="px-2 py-2">What it means</th>
                  <th className="px-2 py-2">Items</th>
                  <th className="px-2 py-2"> </th>
                </tr>
              </thead>
              <tbody>
                {runsQuery.data.map((row, idx) => (
                  <tr key={row.preview_run_id} className="border-b border-[var(--mm-border)] align-top">
                    <td className="px-2 py-2 text-xs text-[var(--mm-text2)]">{idx + 1}</td>
                    <td className="px-2 py-2 text-xs text-[var(--mm-text2)]">{ruleFamilyColumnLabel(row.rule_family_id)}</td>
                    <td className="whitespace-nowrap px-2 py-2 text-xs text-[var(--mm-text2)]">{fmt(row.created_at)}</td>
                    <td className="max-w-[14rem] break-words px-2 py-2 text-xs">
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
                    <td className="whitespace-nowrap px-2 py-2 text-xs">
                      {row.candidate_count}
                      {row.truncated ? " (list stopped at limit)" : ""}
                    </td>
                    <td className="px-2 py-2 space-y-1">
                      <button
                        type="button"
                        className="rounded border border-[var(--mm-border)] px-2 py-1 text-xs font-medium text-[var(--mm-text)] disabled:opacity-50"
                        disabled={busy}
                        onClick={() => void loadJsonFor(row.preview_run_id)}
                      >
                        Raw
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
            No scans yet for this tab. Run a scan from a rule panel above; when it finishes, rows appear here with the
            result, how many items matched, and a short explanation (including rules Plex does not support).
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
              {applySnapshotOperatorLabel ?? "Delete from last scan"}
            </h3>
            <p className="mt-2 text-sm text-[var(--mm-text2)]">
              This deletes <strong>only</strong> the titles from the saved list you opened — MediaMop does not run a new
              scan or add titles. Items already removed on the server are usually counted as skipped; full counts appear
              in Activity when the job finishes.
            </p>
            {applyEligQuery.isLoading ? (
              <p className="mt-3 text-sm text-[var(--mm-text2)]">Checking whether deletion is allowed…</p>
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
                  Library type: <strong>{applyEligQuery.data.media_scope === "tv" ? "TV shows" : "Movies"}</strong>
                </li>
                <li>
                  Scan time:{" "}
                  {applyEligQuery.data.preview_created_at ? fmt(applyEligQuery.data.preview_created_at) : "—"}
                </li>
                <li>
                  Items in this list: <strong>{applyEligQuery.data.candidate_count}</strong>
                </li>
              </ul>
            ) : null}
            {applyEligQuery.data && !applyEligQuery.data.eligible ? (
              <p className="mt-3 text-sm text-amber-700" role="status">
                {applyEligQuery.data.reasons.length
                  ? applyEligQuery.data.reasons.join(" ")
                  : "These items cannot be deleted right now."}
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
                  I confirm <strong>{applySnapshotOperatorLabel}</strong> for this saved list of up to{" "}
                  {applyEligQuery.data.candidate_count} titles.
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
                {applySnapshotOperatorLabel ?? "Confirm delete"}
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
