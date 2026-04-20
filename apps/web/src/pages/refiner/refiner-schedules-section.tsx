import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { MmOnOffSwitch } from "../../components/ui/mm-on-off-switch";
import {
  MM_SCHEDULE_TIME_WINDOW_HEADING,
  MM_SCHEDULE_TIME_WINDOW_HELPER,
  MmScheduleDayChips,
  MmScheduleTimeFields,
} from "../../components/ui/mm-schedule-window-controls";
import { PageLoading } from "../../components/shared/page-loading";
import { isHttpErrorFromApi, isLikelyNetworkFailure } from "../../lib/api/error-guards";
import { useMeQuery } from "../../lib/auth/queries";
import {
  useRefinerOperatorSettingsQuery,
  useRefinerOperatorSettingsSaveMutation,
  useRefinerPathSettingsQuery,
  useRefinerWatchedFolderRemuxScanDispatchEnqueueMutation,
} from "../../lib/refiner/queries";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import {
  FETCHER_TAB_PANEL_BLURB_CLASS,
  FETCHER_TAB_PANEL_INTRO_CLASS,
  FETCHER_TAB_PANEL_TITLE_CLASS,
} from "../fetcher/fetcher-tab-panel-intro";

const RUN_INTERVAL_HELPER = "How often this search runs automatically.";
const SCHED_INTERVAL_MIN_MINUTES = 1;
const SCHED_INTERVAL_MAX_MINUTES = 7 * 24 * 60;

function canEdit(role: string | undefined): boolean {
  return role === "operator" || role === "admin";
}

function RefinerScheduleLaneCard({
  sectionTitle,
  sectionIntro,
  idPrefix,
  timedEnabled,
  onTimedEnabled,
  intervalMinutes,
  onIntervalMinutes,
  hoursLimited,
  onHoursLimited,
  scheduleDays,
  onScheduleDays,
  scheduleStart,
  scheduleEnd,
  onScheduleStart,
  onScheduleEnd,
  disabled,
  footer,
}: {
  sectionTitle: string;
  sectionIntro: string;
  idPrefix: string;
  timedEnabled: boolean;
  onTimedEnabled: (v: boolean) => void;
  intervalMinutes: number;
  onIntervalMinutes: (v: number) => void;
  hoursLimited: boolean;
  onHoursLimited: (v: boolean) => void;
  scheduleDays: string;
  onScheduleDays: (csv: string) => void;
  scheduleStart: string;
  scheduleEnd: string;
  onScheduleStart: (hhmm: string) => void;
  onScheduleEnd: (hhmm: string) => void;
  disabled: boolean;
  footer?: ReactNode;
}) {
  return (
    <section className="mm-card mm-dash-card flex h-full min-h-0 min-w-0 flex-col gap-7">
      <div>
        <h3 className="text-base font-semibold text-[var(--mm-text1)]">{sectionTitle}</h3>
        <p className="mt-1 text-sm text-[var(--mm-text2)]">{sectionIntro}</p>
      </div>
      <MmOnOffSwitch
        id={`${idPrefix}-timed`}
        label="Enable timed scans"
        enabled={timedEnabled}
        disabled={disabled}
        onChange={onTimedEnabled}
      />
      <div>
        <span className="text-sm font-medium text-[var(--mm-text1)]">Run interval (minutes)</span>
        <p className="mt-1 text-xs text-[var(--mm-text3)]">{RUN_INTERVAL_HELPER}</p>
        <input
          type="number"
          min={SCHED_INTERVAL_MIN_MINUTES}
          max={SCHED_INTERVAL_MAX_MINUTES}
          className="mm-input mt-2 w-full"
          value={intervalMinutes}
          disabled={disabled}
          onChange={(e) =>
            onIntervalMinutes(
              Math.max(
                SCHED_INTERVAL_MIN_MINUTES,
                Math.min(SCHED_INTERVAL_MAX_MINUTES, Number(e.target.value) || SCHED_INTERVAL_MIN_MINUTES),
              ),
            )
          }
        />
      </div>
      <div className="space-y-3">
        <div>
          <span className="text-sm font-medium text-[var(--mm-text1)]">{MM_SCHEDULE_TIME_WINDOW_HEADING}</span>
          <p className="mt-1 text-xs text-[var(--mm-text3)]">{MM_SCHEDULE_TIME_WINDOW_HELPER}</p>
        </div>
        <div className="space-y-4">
          <MmOnOffSwitch
            id={`${idPrefix}-hours-limited`}
            label="Limit to these hours"
            enabled={hoursLimited}
            disabled={disabled}
            onChange={onHoursLimited}
          />
          <div className="space-y-2">
            <span className="text-sm font-medium text-[var(--mm-text1)]">Days</span>
            <MmScheduleDayChips scheduleDaysCsv={scheduleDays} disabled={disabled} onChangeCsv={onScheduleDays} />
          </div>
          <MmScheduleTimeFields
            idPrefix={idPrefix}
            start={scheduleStart}
            end={scheduleEnd}
            disabled={disabled}
            onStart={onScheduleStart}
            onEnd={onScheduleEnd}
          />
        </div>
      </div>
      {footer !== undefined && footer !== null ? (
        <div className="border-t border-[var(--mm-border)] pt-5">{footer}</div>
      ) : null}
    </section>
  );
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

  const [tvEnabled, setTvEnabled] = useState(true);
  const [tvIntervalMin, setTvIntervalMin] = useState(5);
  const [tvHoursLimited, setTvHoursLimited] = useState(false);
  const [tvDays, setTvDays] = useState("");
  const [tvStart, setTvStart] = useState("00:00");
  const [tvEnd, setTvEnd] = useState("23:59");

  const [movieEnabled, setMovieEnabled] = useState(true);
  const [movieIntervalMin, setMovieIntervalMin] = useState(5);
  const [movieHoursLimited, setMovieHoursLimited] = useState(false);
  const [movieDays, setMovieDays] = useState("");
  const [movieStart, setMovieStart] = useState("00:00");
  const [movieEnd, setMovieEnd] = useState("23:59");

  const tvIntervalSeconds = Math.max(60, Math.min(7 * 24 * 3600, tvIntervalMin * 60));
  const movieIntervalSeconds = Math.max(60, Math.min(7 * 24 * 3600, movieIntervalMin * 60));

  const movieDirty =
    q.data !== undefined &&
    (movieEnabled !== q.data.movie_schedule_enabled ||
      movieIntervalSeconds !== q.data.movie_schedule_interval_seconds ||
      movieHoursLimited !== q.data.movie_schedule_hours_limited ||
      movieDays !== q.data.movie_schedule_days ||
      movieStart !== q.data.movie_schedule_start ||
      movieEnd !== q.data.movie_schedule_end);

  const tvDirty =
    q.data !== undefined &&
    (tvEnabled !== q.data.tv_schedule_enabled ||
      tvIntervalSeconds !== q.data.tv_schedule_interval_seconds ||
      tvHoursLimited !== q.data.tv_schedule_hours_limited ||
      tvDays !== q.data.tv_schedule_days ||
      tvStart !== q.data.tv_schedule_start ||
      tvEnd !== q.data.tv_schedule_end);

  const scheduleHydratedRef = useRef(false);

  useEffect(() => {
    if (!q.data) {
      return;
    }
    if (!scheduleHydratedRef.current) {
      setMovieEnabled(q.data.movie_schedule_enabled);
      setMovieIntervalMin(Math.max(1, Math.round(q.data.movie_schedule_interval_seconds / 60)));
      setMovieHoursLimited(q.data.movie_schedule_hours_limited);
      setMovieDays(q.data.movie_schedule_days);
      setMovieStart(q.data.movie_schedule_start);
      setMovieEnd(q.data.movie_schedule_end);
      setTvEnabled(q.data.tv_schedule_enabled);
      setTvIntervalMin(Math.max(1, Math.round(q.data.tv_schedule_interval_seconds / 60)));
      setTvHoursLimited(q.data.tv_schedule_hours_limited);
      setTvDays(q.data.tv_schedule_days);
      setTvStart(q.data.tv_schedule_start);
      setTvEnd(q.data.tv_schedule_end);
      scheduleHydratedRef.current = true;
      return;
    }
    if (!movieDirty) {
      setMovieEnabled(q.data.movie_schedule_enabled);
      setMovieIntervalMin(Math.max(1, Math.round(q.data.movie_schedule_interval_seconds / 60)));
      setMovieHoursLimited(q.data.movie_schedule_hours_limited);
      setMovieDays(q.data.movie_schedule_days);
      setMovieStart(q.data.movie_schedule_start);
      setMovieEnd(q.data.movie_schedule_end);
    }
    if (!tvDirty) {
      setTvEnabled(q.data.tv_schedule_enabled);
      setTvIntervalMin(Math.max(1, Math.round(q.data.tv_schedule_interval_seconds / 60)));
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
      <div className="mm-fetcher-module-surface w-full min-w-0 rounded border border-red-900/40 bg-red-950/20 p-4 text-sm text-red-200" role="alert">
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
    <section className="mm-fetcher-module-surface mb-6 w-full min-w-0" data-testid="refiner-schedules-section">
      <header className={FETCHER_TAB_PANEL_INTRO_CLASS}>
        <h2 id="mm-refiner-schedules-heading" className={FETCHER_TAB_PANEL_TITLE_CLASS}>
          Schedules
        </h2>
        <p className={FETCHER_TAB_PANEL_BLURB_CLASS}>
          Turn periodic watched-folder scans on or off, set how often they run, and limit runs to certain days and times.
          Folder poll cadence is still configured under Libraries. Nothing here affects Fetcher.
        </p>
      </header>

      <div className="mm-dash-grid gap-x-5 gap-y-6">
        <RefinerScheduleLaneCard
          sectionTitle="TV watched-folder scans"
          sectionIntro="When and how often Refiner may enqueue periodic TV watched-folder scan jobs."
          idPrefix="refiner-schedule-tv"
          timedEnabled={tvEnabled}
          onTimedEnabled={setTvEnabled}
          intervalMinutes={tvIntervalMin}
          onIntervalMinutes={setTvIntervalMin}
          hoursLimited={tvHoursLimited}
          onHoursLimited={setTvHoursLimited}
          scheduleDays={tvDays}
          onScheduleDays={setTvDays}
          scheduleStart={tvStart}
          scheduleEnd={tvEnd}
          onScheduleStart={setTvStart}
          onScheduleEnd={setTvEnd}
          disabled={!editable || saveTvSchedule.isPending}
          footer={
            <button
              type="button"
              className={`${mmActionButtonClass({
                variant: "primary",
                disabled: !editable || !tvDirty || saveTvSchedule.isPending,
              })} w-full`}
              disabled={!editable || !tvDirty || saveTvSchedule.isPending}
              onClick={() =>
                saveTvSchedule.mutate({
                  tv_schedule_enabled: tvEnabled,
                  tv_schedule_interval_seconds: tvIntervalSeconds,
                  tv_schedule_hours_limited: tvHoursLimited,
                  tv_schedule_days: tvDays,
                  tv_schedule_start: tvStart,
                  tv_schedule_end: tvEnd,
                })
              }
            >
              {saveTvSchedule.isPending ? "Saving…" : "Save TV schedule"}
            </button>
          }
        />
        <RefinerScheduleLaneCard
          sectionTitle="Movies watched-folder scans"
          sectionIntro="When and how often Refiner may enqueue periodic Movies watched-folder scan jobs."
          idPrefix="refiner-schedule-movies"
          timedEnabled={movieEnabled}
          onTimedEnabled={setMovieEnabled}
          intervalMinutes={movieIntervalMin}
          onIntervalMinutes={setMovieIntervalMin}
          hoursLimited={movieHoursLimited}
          onHoursLimited={setMovieHoursLimited}
          scheduleDays={movieDays}
          onScheduleDays={setMovieDays}
          scheduleStart={movieStart}
          scheduleEnd={movieEnd}
          onScheduleStart={setMovieStart}
          onScheduleEnd={setMovieEnd}
          disabled={!editable || saveMovieSchedule.isPending}
          footer={
            <button
              type="button"
              className={`${mmActionButtonClass({
                variant: "primary",
                disabled: !editable || !movieDirty || saveMovieSchedule.isPending,
              })} w-full`}
              disabled={!editable || !movieDirty || saveMovieSchedule.isPending}
              onClick={() =>
                saveMovieSchedule.mutate({
                  movie_schedule_enabled: movieEnabled,
                  movie_schedule_interval_seconds: movieIntervalSeconds,
                  movie_schedule_hours_limited: movieHoursLimited,
                  movie_schedule_days: movieDays,
                  movie_schedule_start: movieStart,
                  movie_schedule_end: movieEnd,
                })
              }
            >
              {saveMovieSchedule.isPending ? "Saving…" : "Save Movies schedule"}
            </button>
          }
        />
      </div>

      <section className="mm-card mm-dash-card mt-7 p-5 sm:p-6">
        <h3 className="text-base font-semibold text-[var(--mm-text1)]">Run now</h3>
        <p className="mt-1 text-sm text-[var(--mm-text2)]">
          Run a scan immediately without waiting for the next folder poll or window.
        </p>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div className="rounded-md border border-[var(--mm-border)] bg-black/10 p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">TV</p>
            <p className="mt-1 text-xs text-[var(--mm-text3)]">
              Queues only the TV watched-folder scan job. Does not queue Movies.
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
                onClick={() => queueTvScan.mutate({ enqueue_remux_jobs: false, media_scope: "tv" })}
              >
                {queueTvScan.isPending ? "Queuing TV scan…" : "Run TV scan now"}
              </button>
            </div>
          </div>
          <div className="rounded-md border border-[var(--mm-border)] bg-black/10 p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">Movies</p>
            <p className="mt-1 text-xs text-[var(--mm-text3)]">
              Queues only the Movies watched-folder scan job. Does not queue TV.
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
                onClick={() => queueMovieScan.mutate({ enqueue_remux_jobs: false, media_scope: "movie" })}
              >
                {queueMovieScan.isPending ? "Queuing Movies scan…" : "Run Movies scan now"}
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
          {saveTvSchedule.error instanceof Error ? saveTvSchedule.error.message : "Save TV schedule failed."}
        </p>
      ) : null}
      {saveMovieSchedule.isError ? (
        <p className="mt-3 text-sm text-red-300" role="alert">
          {saveMovieSchedule.error instanceof Error ? saveMovieSchedule.error.message : "Save Movies schedule failed."}
        </p>
      ) : null}
    </section>
  );
}
