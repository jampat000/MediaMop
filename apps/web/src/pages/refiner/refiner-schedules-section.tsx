import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { MmScheduleDayChips, MmScheduleTimeFields } from "../../components/ui/mm-schedule-window-controls";
import { MmOnOffSwitch } from "../../components/ui/mm-on-off-switch";
import { PageLoading } from "../../components/shared/page-loading";
import { isHttpErrorFromApi, isLikelyNetworkFailure } from "../../lib/api/error-guards";
import { useMeQuery } from "../../lib/auth/queries";
import {
  useRefinerOperatorSettingsQuery,
  useRefinerOperatorSettingsSaveMutation,
  useRefinerPathSettingsQuery,
  useRefinerWatchedFolderRemuxScanDispatchEnqueueMutation,
} from "../../lib/refiner/queries";
import { timezoneDisplayLabelForUi } from "../../lib/suite/timezone-options";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";

function canEdit(role: string | undefined): boolean {
  return role === "operator" || role === "admin";
}

const RUN_INTERVAL_MIN_MINUTES = 1;
const RUN_INTERVAL_MAX_MINUTES = 7 * 24 * 60;
const DEFAULT_RUN_INTERVAL_MINUTES = 5;

function committedRunIntervalMinutes(seconds: number): string {
  return String(Math.max(RUN_INTERVAL_MIN_MINUTES, Math.round(seconds / 60)));
}

function finalizeRunIntervalMinutesDraft(draft: string, committedSeconds: number): number {
  const raw = draft.trim();
  if (raw === "") {
    return Math.max(60, committedSeconds);
  }
  const minutes = Number(raw);
  if (!Number.isFinite(minutes)) {
    return Math.max(60, committedSeconds);
  }
  const clamped = Math.min(RUN_INTERVAL_MAX_MINUTES, Math.max(RUN_INTERVAL_MIN_MINUTES, Math.round(minutes)));
  return clamped * 60;
}

function RefinerScopeScheduleCard({
  title,
  idPrefix,
  enabled,
  onEnabled,
  runIntervalMinutesDraft,
  runIntervalCommittedSeconds,
  onRunIntervalDraft,
  onCommitRunIntervalBlur,
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
  title: string;
  idPrefix: string;
  enabled: boolean;
  onEnabled: (v: boolean) => void;
  runIntervalMinutesDraft: string | null;
  runIntervalCommittedSeconds: number;
  onRunIntervalDraft: (v: string | null) => void;
  onCommitRunIntervalBlur: () => void;
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
    <section className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-6">
      <h3 className="text-sm font-semibold text-[var(--mm-text1)]">{title}</h3>
      <div className="mt-5 space-y-6">
        <MmOnOffSwitch
          id={`${idPrefix}-timed-enabled`}
          label="Enable timed scans"
          enabled={enabled}
          disabled={disabled}
          onChange={onEnabled}
        />
        <div>
          <span className="text-sm font-medium text-[var(--mm-text1)]">Run interval (minutes)</span>
          <p className="mt-1 text-xs leading-relaxed text-[var(--mm-text3)]">
            How often this runs automatically.
          </p>
          <input
            type="number"
            min={RUN_INTERVAL_MIN_MINUTES}
            max={RUN_INTERVAL_MAX_MINUTES}
            className="mm-input mt-2 w-full"
            value={
              runIntervalMinutesDraft !== null
                ? runIntervalMinutesDraft
                : committedRunIntervalMinutes(runIntervalCommittedSeconds)
            }
            onFocus={() => onRunIntervalDraft(committedRunIntervalMinutes(runIntervalCommittedSeconds))}
            onChange={(e) => onRunIntervalDraft(e.target.value)}
            onBlur={() => onCommitRunIntervalBlur()}
            disabled={disabled}
          />
        </div>
        <div className="space-y-3">
          <div>
            <span className="text-sm font-medium text-[var(--mm-text1)]">Time window</span>
            <p className="mt-1 text-xs leading-relaxed text-[var(--mm-text3)]">
              When limiting is on, this only runs inside the window you set below.
            </p>
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
      </div>
      {footer !== undefined && footer !== null ? <div className="mt-6 border-t border-[var(--mm-border)] pt-5">{footer}</div> : null}
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

  const [movieEnabled, setMovieEnabled] = useState(true);
  const [movieIntervalDraft, setMovieIntervalDraft] = useState<string | null>(null);
  const [movieIntervalSeconds, setMovieIntervalSeconds] = useState(DEFAULT_RUN_INTERVAL_MINUTES * 60);
  const [movieHoursLimited, setMovieHoursLimited] = useState(false);
  const [movieDays, setMovieDays] = useState("");
  const [movieStart, setMovieStart] = useState("00:00");
  const [movieEnd, setMovieEnd] = useState("23:59");

  const [tvEnabled, setTvEnabled] = useState(true);
  const [tvIntervalDraft, setTvIntervalDraft] = useState<string | null>(null);
  const [tvIntervalSeconds, setTvIntervalSeconds] = useState(DEFAULT_RUN_INTERVAL_MINUTES * 60);
  const [tvHoursLimited, setTvHoursLimited] = useState(false);
  const [tvDays, setTvDays] = useState("");
  const [tvStart, setTvStart] = useState("00:00");
  const [tvEnd, setTvEnd] = useState("23:59");

  const resolvedMovieIntervalSec =
    movieIntervalDraft !== null
      ? finalizeRunIntervalMinutesDraft(movieIntervalDraft, movieIntervalSeconds)
      : movieIntervalSeconds;
  const resolvedTvIntervalSec =
    tvIntervalDraft !== null ? finalizeRunIntervalMinutesDraft(tvIntervalDraft, tvIntervalSeconds) : tvIntervalSeconds;

  const movieDirty =
    q.data !== undefined &&
    (movieEnabled !== q.data.movie_schedule_enabled ||
      resolvedMovieIntervalSec !== q.data.movie_schedule_interval_seconds ||
      movieHoursLimited !== q.data.movie_schedule_hours_limited ||
      movieDays !== q.data.movie_schedule_days ||
      movieStart !== q.data.movie_schedule_start ||
      movieEnd !== q.data.movie_schedule_end);

  const tvDirty =
    q.data !== undefined &&
    (tvEnabled !== q.data.tv_schedule_enabled ||
      resolvedTvIntervalSec !== q.data.tv_schedule_interval_seconds ||
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
      setMovieIntervalSeconds(q.data.movie_schedule_interval_seconds);
      setMovieIntervalDraft(null);
      setMovieHoursLimited(q.data.movie_schedule_hours_limited);
      setMovieDays(q.data.movie_schedule_days);
      setMovieStart(q.data.movie_schedule_start);
      setMovieEnd(q.data.movie_schedule_end);
      setTvEnabled(q.data.tv_schedule_enabled);
      setTvIntervalSeconds(q.data.tv_schedule_interval_seconds);
      setTvIntervalDraft(null);
      setTvHoursLimited(q.data.tv_schedule_hours_limited);
      setTvDays(q.data.tv_schedule_days);
      setTvStart(q.data.tv_schedule_start);
      setTvEnd(q.data.tv_schedule_end);
      scheduleHydratedRef.current = true;
      return;
    }
    if (!movieDirty) {
      setMovieEnabled(q.data.movie_schedule_enabled);
      setMovieIntervalSeconds(q.data.movie_schedule_interval_seconds);
      setMovieIntervalDraft(null);
      setMovieHoursLimited(q.data.movie_schedule_hours_limited);
      setMovieDays(q.data.movie_schedule_days);
      setMovieStart(q.data.movie_schedule_start);
      setMovieEnd(q.data.movie_schedule_end);
    }
    if (!tvDirty) {
      setTvEnabled(q.data.tv_schedule_enabled);
      setTvIntervalSeconds(q.data.tv_schedule_interval_seconds);
      setTvIntervalDraft(null);
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

  const movieMinutesOk =
    movieIntervalDraft === null ||
    (Number.isFinite(Number(movieIntervalDraft.trim() || "0")) &&
      Number(movieIntervalDraft.trim() || "0") >= RUN_INTERVAL_MIN_MINUTES &&
      Number(movieIntervalDraft.trim() || "0") <= RUN_INTERVAL_MAX_MINUTES);
  const tvMinutesOk =
    tvIntervalDraft === null ||
    (Number.isFinite(Number(tvIntervalDraft.trim() || "0")) &&
      Number(tvIntervalDraft.trim() || "0") >= RUN_INTERVAL_MIN_MINUTES &&
      Number(tvIntervalDraft.trim() || "0") <= RUN_INTERVAL_MAX_MINUTES);

  return (
    <section className="mm-fetcher-module-surface w-full min-w-0 rounded border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-6 text-sm leading-relaxed text-[var(--mm-text2)] sm:p-7">
      <h2 className="text-base font-semibold text-[var(--mm-text)]">Schedules</h2>
      <p className="mt-2 max-w-3xl text-[var(--mm-text3)]">
        Set when Refiner runs automatic watched-folder scans for TV and Movies. Nothing here affects Fetcher.
      </p>
      <section
        className="mt-6 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5"
        aria-label="Suite time zone for Refiner schedules"
      >
        <p className="text-sm text-[var(--mm-text2)]">
          <span className="font-medium text-[var(--mm-text1)]">Suite time zone for schedule windows</span>{" "}
          {timezoneDisplayLabelForUi(q.data.schedule_timezone)}
        </p>
        <p className="mt-2 text-xs leading-relaxed text-[var(--mm-text3)]">
          Same clock as Fetcher. Days and hours in each card below are saved separately for TV and Movies.
        </p>
      </section>
      <div className="mt-8 grid gap-6 lg:grid-cols-2 lg:gap-8">
        <RefinerScopeScheduleCard
          title="TV"
          idPrefix="refiner-schedule-tv"
          enabled={tvEnabled}
          onEnabled={setTvEnabled}
          runIntervalMinutesDraft={tvIntervalDraft}
          runIntervalCommittedSeconds={tvIntervalSeconds}
          onRunIntervalDraft={setTvIntervalDraft}
          onCommitRunIntervalBlur={() => {
            const next = finalizeRunIntervalMinutesDraft(
              tvIntervalDraft !== null ? tvIntervalDraft : committedRunIntervalMinutes(tvIntervalSeconds),
              tvIntervalSeconds,
            );
            setTvIntervalDraft(null);
            if (next !== tvIntervalSeconds) {
              setTvIntervalSeconds(next);
            }
          }}
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
              className={mmActionButtonClass({
                variant: "primary",
                disabled: !editable || !tvDirty || !tvMinutesOk || saveTvSchedule.isPending,
              })}
              disabled={!editable || !tvDirty || !tvMinutesOk || saveTvSchedule.isPending}
              onClick={() =>
                saveTvSchedule.mutate({
                  tv_schedule_enabled: tvEnabled,
                  tv_schedule_interval_seconds: resolvedTvIntervalSec,
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
        <RefinerScopeScheduleCard
          title="Movies"
          idPrefix="refiner-schedule-movies"
          enabled={movieEnabled}
          onEnabled={setMovieEnabled}
          runIntervalMinutesDraft={movieIntervalDraft}
          runIntervalCommittedSeconds={movieIntervalSeconds}
          onRunIntervalDraft={setMovieIntervalDraft}
          onCommitRunIntervalBlur={() => {
            const next = finalizeRunIntervalMinutesDraft(
              movieIntervalDraft !== null ? movieIntervalDraft : committedRunIntervalMinutes(movieIntervalSeconds),
              movieIntervalSeconds,
            );
            setMovieIntervalDraft(null);
            if (next !== movieIntervalSeconds) {
              setMovieIntervalSeconds(next);
            }
          }}
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
              className={mmActionButtonClass({
                variant: "primary",
                disabled: !editable || !movieDirty || !movieMinutesOk || saveMovieSchedule.isPending,
              })}
              disabled={!editable || !movieDirty || !movieMinutesOk || saveMovieSchedule.isPending}
              onClick={() =>
                saveMovieSchedule.mutate({
                  movie_schedule_enabled: movieEnabled,
                  movie_schedule_interval_seconds: resolvedMovieIntervalSec,
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
      <section className="mt-7 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5">
        <h3 className="text-sm font-semibold text-[var(--mm-text)]">Run now</h3>
        <p className="mt-1 text-xs leading-relaxed text-[var(--mm-text3)]">
          Run a scan immediately without waiting for the schedule.
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
