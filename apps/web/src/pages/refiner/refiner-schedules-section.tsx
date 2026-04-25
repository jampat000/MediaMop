import { useEffect, useRef, useState } from "react";
import { PageLoading } from "../../components/shared/page-loading";
import { isHttpErrorFromApi, isLikelyNetworkFailure } from "../../lib/api/error-guards";
import { useMeQuery } from "../../lib/auth/queries";
import {
  MM_SCHEDULE_TIME_WINDOW_HELPER,
  MmScheduleDayChips,
  MmScheduleTimeFields,
} from "../../components/ui/mm-schedule-window-controls";
import { MmOnOffSwitch } from "../../components/ui/mm-on-off-switch";
import {
  useRefinerOperatorSettingsQuery,
  useRefinerOperatorSettingsSaveMutation,
  useRefinerPathSettingsQuery,
  useRefinerWatchedFolderRemuxScanDispatchEnqueueMutation,
} from "../../lib/refiner/queries";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";

function canEdit(role: string | undefined): boolean {
  return role === "operator" || role === "admin";
}

export function RefinerSchedulesSection() {
  const me = useMeQuery();
  const q = useRefinerOperatorSettingsQuery();
  const pathSettings = useRefinerPathSettingsQuery();
  const saveTvSchedule = useRefinerOperatorSettingsSaveMutation();
  const saveMovieSchedule = useRefinerOperatorSettingsSaveMutation();
  const queueTvScan = useRefinerWatchedFolderRemuxScanDispatchEnqueueMutation();
  const queueMovieScan = useRefinerWatchedFolderRemuxScanDispatchEnqueueMutation();
  const editable = canEdit(me.data?.role);
  const [tvHoursLimited, setTvHoursLimited] = useState(false);
  const [tvDays, setTvDays] = useState("");
  const [tvStart, setTvStart] = useState("00:00");
  const [tvEnd, setTvEnd] = useState("23:59");
  const [movieHoursLimited, setMovieHoursLimited] = useState(false);
  const [movieDays, setMovieDays] = useState("");
  const [movieStart, setMovieStart] = useState("00:00");
  const [movieEnd, setMovieEnd] = useState("23:59");
  const scheduleHydratedRef = useRef(false);

  const movieDirty =
    q.data !== undefined &&
    (movieHoursLimited !== q.data.movie_schedule_hours_limited ||
      movieDays !== q.data.movie_schedule_days ||
      movieStart !== q.data.movie_schedule_start ||
      movieEnd !== q.data.movie_schedule_end);

  const tvDirty =
    q.data !== undefined &&
    (tvHoursLimited !== q.data.tv_schedule_hours_limited ||
      tvDays !== q.data.tv_schedule_days ||
      tvStart !== q.data.tv_schedule_start ||
      tvEnd !== q.data.tv_schedule_end);

  useEffect(() => {
    if (!q.data) {
      return;
    }
    if (!scheduleHydratedRef.current) {
      setMovieHoursLimited(q.data.movie_schedule_hours_limited);
      setMovieDays(q.data.movie_schedule_days);
      setMovieStart(q.data.movie_schedule_start);
      setMovieEnd(q.data.movie_schedule_end);
      setTvHoursLimited(q.data.tv_schedule_hours_limited);
      setTvDays(q.data.tv_schedule_days);
      setTvStart(q.data.tv_schedule_start);
      setTvEnd(q.data.tv_schedule_end);
      scheduleHydratedRef.current = true;
      return;
    }
    if (!movieDirty) {
      setMovieHoursLimited(q.data.movie_schedule_hours_limited);
      setMovieDays(q.data.movie_schedule_days);
      setMovieStart(q.data.movie_schedule_start);
      setMovieEnd(q.data.movie_schedule_end);
    }
    if (!tvDirty) {
      setTvHoursLimited(q.data.tv_schedule_hours_limited);
      setTvDays(q.data.tv_schedule_days);
      setTvStart(q.data.tv_schedule_start);
      setTvEnd(q.data.tv_schedule_end);
    }
  }, [q.data, movieDirty, tvDirty]);

  if (q.isPending || pathSettings.isPending || me.isPending) {
    return <PageLoading label="Loading Refiner schedules" />;
  }
  if (q.isError || pathSettings.isError) {
    return (
      <div className="mm-module-surface w-full min-w-0 rounded border border-red-900/40 bg-red-950/20 p-4 text-sm text-red-200" role="alert">
        <p className="font-semibold">Could not load Refiner schedules</p>
        <p className="mt-1">
          {isLikelyNetworkFailure(q.error ?? pathSettings.error)
            ? "Check that the MediaMop API is running."
            : isHttpErrorFromApi(q.error ?? pathSettings.error)
              ? "Sign in, then try again."
              : "Request failed."}
        </p>
      </div>
    );
  }
  if (!q.data || !pathSettings.data) {
    return null;
  }

  const canQueueManual = editable;
  const tvWatchedSet = Boolean((pathSettings.data.refiner_tv_watched_folder ?? "").trim());
  const movieWatchedSet = Boolean((pathSettings.data.refiner_watched_folder ?? "").trim());

  return (
    <section className="mm-bubble-stack mm-module-surface w-full min-w-0" data-testid="refiner-schedules-section">
      <div className="mm-dash-grid">
        <section className="mm-card mm-dash-card flex h-full min-h-0 min-w-0 flex-col">
          <div className="mm-card-action-body flex-1 min-h-0">
          <div>
            <h3 className="text-base font-semibold text-[var(--mm-text1)]">TV watched-folder window</h3>
            <p className="mt-1 text-sm text-[var(--mm-text2)]">
              Optional window for TV watched-folder checks from Libraries.
            </p>
          </div>
          <div className="space-y-3">
            <div>
              <span className="text-sm font-medium text-[var(--mm-text1)]">Schedule window</span>
              <p className="mt-1 text-xs text-[var(--mm-text3)]">{MM_SCHEDULE_TIME_WINDOW_HELPER}</p>
            </div>
            <div className="space-y-4">
              <MmOnOffSwitch
                id="refiner-schedule-tv-hours-limited"
                label="Limit to these hours"
                enabled={tvHoursLimited}
                disabled={!editable || saveTvSchedule.isPending}
                onChange={setTvHoursLimited}
              />
              <div className="space-y-2">
                <span className="text-sm font-medium text-[var(--mm-text1)]">Days</span>
                <MmScheduleDayChips
                  scheduleDaysCsv={tvDays}
                  disabled={!editable || saveTvSchedule.isPending}
                  onChangeCsv={setTvDays}
                />
              </div>
              <MmScheduleTimeFields
                idPrefix="refiner-schedule-tv-window"
                start={tvStart}
                end={tvEnd}
                disabled={!editable || saveTvSchedule.isPending}
                onStart={setTvStart}
                onEnd={setTvEnd}
              />
            </div>
          </div>
          </div>
          <div className="mm-card-action-footer">
            <button
              type="button"
              className={`${mmActionButtonClass({
                variant: "primary",
                disabled: !editable || !tvDirty || saveTvSchedule.isPending,
              })} w-full`}
              disabled={!editable || !tvDirty || saveTvSchedule.isPending}
              onClick={() =>
                saveTvSchedule.mutate({
                  tv_schedule_enabled: q.data.tv_schedule_enabled,
                  tv_schedule_hours_limited: tvHoursLimited,
                  tv_schedule_days: tvDays,
                  tv_schedule_start: tvStart,
                  tv_schedule_end: tvEnd,
                })
              }
            >
              {saveTvSchedule.isPending ? "Saving…" : "Save TV schedule window"}
            </button>
          </div>
        </section>
        <section className="mm-card mm-dash-card flex h-full min-h-0 min-w-0 flex-col">
          <div className="mm-card-action-body flex-1 min-h-0">
          <div>
            <h3 className="text-base font-semibold text-[var(--mm-text1)]">Movies watched-folder window</h3>
            <p className="mt-1 text-sm text-[var(--mm-text2)]">
              Optional window for Movies watched-folder checks from Libraries.
            </p>
          </div>
          <div className="space-y-3">
            <div>
              <span className="text-sm font-medium text-[var(--mm-text1)]">Schedule window</span>
              <p className="mt-1 text-xs text-[var(--mm-text3)]">{MM_SCHEDULE_TIME_WINDOW_HELPER}</p>
            </div>
            <div className="space-y-4">
              <MmOnOffSwitch
                id="refiner-schedule-movie-hours-limited"
                label="Limit to these hours"
                enabled={movieHoursLimited}
                disabled={!editable || saveMovieSchedule.isPending}
                onChange={setMovieHoursLimited}
              />
              <div className="space-y-2">
                <span className="text-sm font-medium text-[var(--mm-text1)]">Days</span>
                <MmScheduleDayChips
                  scheduleDaysCsv={movieDays}
                  disabled={!editable || saveMovieSchedule.isPending}
                  onChangeCsv={setMovieDays}
                />
              </div>
              <MmScheduleTimeFields
                idPrefix="refiner-schedule-movie-window"
                start={movieStart}
                end={movieEnd}
                disabled={!editable || saveMovieSchedule.isPending}
                onStart={setMovieStart}
                onEnd={setMovieEnd}
              />
            </div>
          </div>
          </div>
          <div className="mm-card-action-footer">
            <button
              type="button"
              className={`${mmActionButtonClass({
                variant: "primary",
                disabled: !editable || !movieDirty || saveMovieSchedule.isPending,
              })} w-full`}
              disabled={!editable || !movieDirty || saveMovieSchedule.isPending}
              onClick={() =>
                saveMovieSchedule.mutate({
                  movie_schedule_enabled: q.data.movie_schedule_enabled,
                  movie_schedule_hours_limited: movieHoursLimited,
                  movie_schedule_days: movieDays,
                  movie_schedule_start: movieStart,
                  movie_schedule_end: movieEnd,
                })
              }
            >
              {saveMovieSchedule.isPending ? "Saving…" : "Save Movies schedule window"}
            </button>
          </div>
        </section>
      </div>

      <section className="mm-card mm-dash-card p-5 sm:p-6">
        <h3 className="text-base font-semibold text-[var(--mm-text1)]">Run now</h3>
        <p className="mt-1 text-sm text-[var(--mm-text2)]">
          Run a scan immediately without waiting for the next folder poll or window.
        </p>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div className="rounded-md border border-[var(--mm-border)] bg-black/10 p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">TV</p>
            <p className="mt-1 text-xs text-[var(--mm-text3)]">
              Checks the TV watched folder now and adds any ready files to Refiner.
            </p>
            {!tvWatchedSet ? (
              <p className="mt-2 text-xs text-amber-200/90">Save a TV watched folder in Libraries before running this scan.</p>
            ) : null}
            {queueTvScan.isError ? (
              <p className="mt-2 text-xs text-red-300" role="alert">
                {queueTvScan.error instanceof Error ? queueTvScan.error.message : "Queue TV scan failed."}
              </p>
            ) : null}
            {queueTvScan.isSuccess ? (
              <p className="mt-2 text-xs text-[var(--mm-text3)]">Queued TV scan job #{queueTvScan.data.job_id}.</p>
            ) : null}
            <div className="mt-3">
              <button
                type="button"
                className={mmActionButtonClass({
                  variant: "secondary",
                  disabled: !canQueueManual || !tvWatchedSet || queueTvScan.isPending,
                })}
                disabled={!canQueueManual || !tvWatchedSet || queueTvScan.isPending}
                onClick={() => queueTvScan.mutate({ enqueue_remux_jobs: true, media_scope: "tv" })}
              >
                {queueTvScan.isPending ? "Starting TV scan..." : "Scan TV now"}
              </button>
            </div>
          </div>
          <div className="rounded-md border border-[var(--mm-border)] bg-black/10 p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">Movies</p>
            <p className="mt-1 text-xs text-[var(--mm-text3)]">
              Checks the Movies watched folder now and adds any ready files to Refiner.
            </p>
            {!movieWatchedSet ? (
              <p className="mt-2 text-xs text-amber-200/90">Save a Movies watched folder in Libraries before running this scan.</p>
            ) : null}
            {queueMovieScan.isError ? (
              <p className="mt-2 text-xs text-red-300" role="alert">
                {queueMovieScan.error instanceof Error ? queueMovieScan.error.message : "Queue Movies scan failed."}
              </p>
            ) : null}
            {queueMovieScan.isSuccess ? (
              <p className="mt-2 text-xs text-[var(--mm-text3)]">Queued Movies scan job #{queueMovieScan.data.job_id}.</p>
            ) : null}
            <div className="mt-3">
              <button
                type="button"
                className={mmActionButtonClass({
                  variant: "secondary",
                  disabled: !canQueueManual || !movieWatchedSet || queueMovieScan.isPending,
                })}
                disabled={!canQueueManual || !movieWatchedSet || queueMovieScan.isPending}
                onClick={() => queueMovieScan.mutate({ enqueue_remux_jobs: true, media_scope: "movie" })}
              >
                {queueMovieScan.isPending ? "Starting Movies scan..." : "Scan Movies now"}
              </button>
            </div>
          </div>
        </div>
        {!canQueueManual ? (
          <p className="mt-3 text-xs text-[var(--mm-text3)]">Operators and admins can queue manual scans.</p>
        ) : null}
      </section>
      {saveTvSchedule.isError ? (
        <p className="mt-3 text-sm text-red-300" role="alert">
          {saveTvSchedule.error instanceof Error ? saveTvSchedule.error.message : "Save TV schedule window failed."}
        </p>
      ) : null}
      {saveMovieSchedule.isError ? (
        <p className="mt-3 text-sm text-red-300" role="alert">
          {saveMovieSchedule.error instanceof Error ? saveMovieSchedule.error.message : "Save Movies schedule window failed."}
        </p>
      ) : null}
    </section>
  );
}
