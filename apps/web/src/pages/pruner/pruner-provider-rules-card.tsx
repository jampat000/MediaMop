import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useState,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { fetchCsrfToken } from "../../lib/api/auth-api";
import { useMeQuery } from "../../lib/auth/queries";
import {
  patchPrunerScope,
  type PrunerServerInstance,
} from "../../lib/pruner/api";
import { prunerGenresFromApi } from "./pruner-genre-multi-select";
import {
  normalizePeopleRolesFromApi,
  peopleRolesForPlexPersist,
  peopleRolesForPlexUiState,
  type PrunerPeopleRoleId,
} from "./pruner-people-roles";
import { PrunerProviderPeopleCard } from "./pruner-provider-people-card";
import {
  parseCommaTokens,
  parsePeopleLines,
} from "./pruner-operator-scan-utils";
import { PrunerProviderRulesMoviesCard } from "./pruner-provider-rules-movies-card";
import { PrunerProviderRulesTvCard } from "./pruner-provider-rules-tv-card";

type ProviderKey = "emby" | "jellyfin" | "plex";

function scopeRow(
  inst: PrunerServerInstance | undefined,
  media_scope: "tv" | "movies",
) {
  return inst?.scopes.find((s) => s.media_scope === media_scope);
}

function parseYear(raw: string): number | null | "bad" {
  const t = raw.trim();
  if (!t) return null;
  const n = Number(t);
  if (!Number.isInteger(n) || n < 1900 || n > 2100) return "bad";
  return n;
}

export { PrunerProviderPeopleCard };

type RulesCardProps = {
  provider: ProviderKey;
  instanceId: number;
  instance: PrunerServerInstance;
};

export type PrunerProviderRulesCardHandle = {
  ensureTvSaved: () => Promise<void>;
  ensureMoviesSaved: () => Promise<void>;
};

export const PrunerProviderRulesCard = forwardRef<
  PrunerProviderRulesCardHandle,
  RulesCardProps
>(function PrunerProviderRulesCard({ provider, instanceId, instance }, ref) {
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
  const [tvRoles, setTvRoles] = useState<PrunerPeopleRoleId[]>([]);

  const [missingPrimaryMovies, setMissingPrimaryMovies] = useState(true);
  const [watchedMovies, setWatchedMovies] = useState(false);
  const [lowRatingMovies, setLowRatingMovies] = useState("0");
  const [unwatchedDays, setUnwatchedDays] = useState("0");
  const [genreMovies, setGenreMovies] = useState<string[]>([]);
  const [yearMinMovies, setYearMinMovies] = useState("");
  const [yearMaxMovies, setYearMaxMovies] = useState("");
  const [studioMovies, setStudioMovies] = useState<string[]>([]);
  const [moviesPeople, setMoviesPeople] = useState("");
  const [moviesRoles, setMoviesRoles] = useState<PrunerPeopleRoleId[]>([]);
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
    setNeverTvDays(
      !tv.never_played_stale_reported_enabled
        ? "0"
        : String(tv.never_played_min_age_days),
    );
    setGenreTv(prunerGenresFromApi(tv.preview_include_genres));
    setYearMinTv(
      tv.preview_year_min != null ? String(tv.preview_year_min) : "",
    );
    setYearMaxTv(
      tv.preview_year_max != null ? String(tv.preview_year_max) : "",
    );
    setStudioTv([...(tv.preview_include_studios ?? [])]);
    setTvPeople(((tv.preview_include_people ?? []) as string[]).join("\n"));
    setTvRoles(
      isPlex
        ? peopleRolesForPlexUiState(tv.preview_include_people_roles)
        : normalizePeopleRolesFromApi(tv.preview_include_people_roles),
    );
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
    setUnwatchedDays(
      !movies.unwatched_movie_stale_reported_enabled
        ? "0"
        : String(movies.unwatched_movie_stale_min_age_days),
    );
    setGenreMovies(prunerGenresFromApi(movies.preview_include_genres));
    setYearMinMovies(
      movies.preview_year_min != null ? String(movies.preview_year_min) : "",
    );
    setYearMaxMovies(
      movies.preview_year_max != null ? String(movies.preview_year_max) : "",
    );
    setStudioMovies([...(movies.preview_include_studios ?? [])]);
    setMoviesPeople(
      ((movies.preview_include_people ?? []) as string[]).join("\n"),
    );
    setMoviesRoles(
      isPlex
        ? peopleRolesForPlexUiState(movies.preview_include_people_roles)
        : normalizePeopleRolesFromApi(movies.preview_include_people_roles),
    );
    setMoviesCollections((movies.preview_include_collections ?? []).join(", "));
  }, [movies, isPlex]);

  const buildFilterPatch = useCallback(
    (
      scope: "tv" | "movies",
      genres: string[],
      yMinStr: string,
      yMaxStrStr: string,
      studios: string[],
      collectionsText?: string,
    ) => {
      const yMin = parseYear(yMinStr);
      const yMax = parseYear(yMaxStrStr);
      if (yMin === "bad" || yMax === "bad") {
        throw new Error(
          "Each year must be a whole number between 1900 and 2100, or left empty.",
        );
      }
      if (yMin != null && yMax != null && yMin > yMax) {
        throw new Error(
          "Minimum year must be less than or equal to maximum year.",
        );
      }
      return {
        preview_include_genres: [...genres],
        preview_year_min: yMinStr.trim() ? yMin : null,
        preview_year_max: yMaxStrStr.trim() ? yMax : null,
        preview_include_studios: [...studios],
        ...(isPlex && scope === "movies"
          ? {
              preview_include_collections: parseCommaTokens(
                collectionsText ?? "",
              ),
            }
          : {}),
      };
    },
    [isPlex],
  );

  const persistTv = useCallback(async (): Promise<void> => {
    if (!tv) return;
    const csrf_token = await fetchCsrfToken();
    const raw = parseInt(neverTvDays.trim(), 10);
    const neverOn = !isPlex && Number.isFinite(raw) && raw >= 7;
    const neverDays = neverOn ? Math.max(7, Math.min(3650, raw)) : 90;
    const filters = buildFilterPatch(
      "tv",
      genreTv,
      yearMinTv,
      yearMaxTv,
      studioTv,
    );
    const rolesPersist = isPlex
      ? peopleRolesForPlexPersist(tvRoles)
      : [...tvRoles];
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
    await qc.invalidateQueries({
      queryKey: ["pruner", "instances", instanceId],
    });
  }, [
    buildFilterPatch,
    tv,
    neverTvDays,
    genreTv,
    yearMinTv,
    yearMaxTv,
    studioTv,
    tvRoles,
    isPlex,
    instanceId,
    missingPrimaryTv,
    watchedTv,
    qc,
    tvPeople,
  ]);

  const persistMovies = useCallback(async (): Promise<void> => {
    if (!movies) return;
    const csrf_token = await fetchCsrfToken();
    const lowRaw = Number.parseFloat(lowRatingMovies.trim());
    const lowOn = Number.isFinite(lowRaw) && lowRaw > 0;
    const cap = lowOn ? Math.max(0, Math.min(10, lowRaw)) : 4;
    const uwRaw = parseInt(unwatchedDays.trim(), 10);
    const uwOn = Number.isFinite(uwRaw) && uwRaw >= 7;
    const uwDays = uwOn ? Math.max(7, Math.min(3650, uwRaw)) : 90;
    const filters = buildFilterPatch(
      "movies",
      genreMovies,
      yearMinMovies,
      yearMaxMovies,
      studioMovies,
      moviesCollections,
    );
    const rolesPersist = isPlex
      ? peopleRolesForPlexPersist(moviesRoles)
      : [...moviesRoles];
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
    await qc.invalidateQueries({
      queryKey: ["pruner", "instances", instanceId],
    });
  }, [
    buildFilterPatch,
    movies,
    lowRatingMovies,
    unwatchedDays,
    genreMovies,
    yearMinMovies,
    yearMaxMovies,
    studioMovies,
    moviesCollections,
    moviesRoles,
    isPlex,
    instanceId,
    missingPrimaryMovies,
    watchedMovies,
    qc,
    moviesPeople,
  ]);

  async function saveTv() {
    if (!tv) return;
    setErrTv(null);
    setMsgTv(null);
    setBusyTv(true);
    try {
      await persistTv();
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
      setMsgMovies("Saved Movies settings.");
    } catch (e) {
      setErrMovies((e as Error).message);
    } finally {
      setBusyMovies(false);
    }
  }

  useImperativeHandle(
    ref,
    () => ({
      ensureTvSaved: persistTv,
      ensureMoviesSaved: persistMovies,
    }),
    [persistMovies, persistTv],
  );

  const tvControlsDisabled = !canOperate || busyTv || busyMovies;
  const moviesControlsDisabled = !canOperate || busyTv || busyMovies;
  const saveDisabledTv = busyTv || !canOperate || instanceId <= 0;
  const saveDisabledMovies = busyMovies || !canOperate || instanceId <= 0;

  const narrowingLabelClass =
    "text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]";

  return (
    <div
      className="mm-bubble-grid lg:grid-cols-2"
      data-testid={`pruner-provider-configuration-${provider}`}
      data-provider-section="cleanup"
    >
      <PrunerProviderRulesTvCard
        provider={provider}
        instanceId={instanceId}
        isPlex={isPlex}
        narrowingLabelClass={narrowingLabelClass}
        tvControlsDisabled={tvControlsDisabled}
        watchedTv={watchedTv}
        setWatchedTv={setWatchedTv}
        neverTvDays={neverTvDays}
        setNeverTvDays={setNeverTvDays}
        missingPrimaryTv={missingPrimaryTv}
        setMissingPrimaryTv={setMissingPrimaryTv}
        genreTv={genreTv}
        setGenreTv={setGenreTv}
        tvPeople={tvPeople}
        setTvPeople={setTvPeople}
        tvRoles={tvRoles}
        setTvRoles={setTvRoles}
        studioTv={studioTv}
        setStudioTv={setStudioTv}
        yearMinTv={yearMinTv}
        setYearMinTv={setYearMinTv}
        yearMaxTv={yearMaxTv}
        setYearMaxTv={setYearMaxTv}
        canOperate={canOperate}
        saveDisabledTv={saveDisabledTv}
        saveTv={saveTv}
        busyTv={busyTv}
        msgTv={msgTv}
        errTv={errTv}
      />

      <PrunerProviderRulesMoviesCard
        provider={provider}
        instanceId={instanceId}
        isPlex={isPlex}
        narrowingLabelClass={narrowingLabelClass}
        moviesControlsDisabled={moviesControlsDisabled}
        watchedMovies={watchedMovies}
        setWatchedMovies={setWatchedMovies}
        lowRatingMovies={lowRatingMovies}
        setLowRatingMovies={setLowRatingMovies}
        unwatchedDays={unwatchedDays}
        setUnwatchedDays={setUnwatchedDays}
        missingPrimaryMovies={missingPrimaryMovies}
        setMissingPrimaryMovies={setMissingPrimaryMovies}
        genreMovies={genreMovies}
        setGenreMovies={setGenreMovies}
        moviesPeople={moviesPeople}
        setMoviesPeople={setMoviesPeople}
        moviesRoles={moviesRoles}
        setMoviesRoles={setMoviesRoles}
        studioMovies={studioMovies}
        setStudioMovies={setStudioMovies}
        yearMinMovies={yearMinMovies}
        setYearMinMovies={setYearMinMovies}
        yearMaxMovies={yearMaxMovies}
        setYearMaxMovies={setYearMaxMovies}
        moviesCollections={moviesCollections}
        setMoviesCollections={setMoviesCollections}
        canOperate={canOperate}
        saveDisabledMovies={saveDisabledMovies}
        saveMovies={saveMovies}
        busyMovies={busyMovies}
        msgMovies={msgMovies}
        errMovies={errMovies}
      />
    </div>
  );
});
