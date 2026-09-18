import { useEffect, useRef, useState } from "react";
import { PageLoading } from "../../components/shared/page-loading";
import {
  QuietSection,
  quietActionRowClass,
} from "../../components/shared/quiet-section";
import {
  isHttpErrorFromApi,
  isLikelyNetworkFailure,
} from "../../lib/api/error-guards";
import { useMeQuery } from "../../lib/auth/queries";
import {
  MM_SCHEDULE_TIME_WINDOW_HELPER,
  MmScheduleDayChips,
  MmScheduleTimeFields,
} from "../../components/ui/mm-schedule-window-controls";
import { MmOnOffSwitch } from "../../components/ui/mm-on-off-switch";
import {
  PROCESSING_MEDIA_TYPE_LABELS,
  type ProcessingLibrary,
} from "../../lib/processing/libraries-api";
import { useProcessingLibrariesQuery } from "../../lib/processing/libraries-queries";
import {
  useProcessingOperatorSettingsQuery,
  useProcessingOperatorSettingsSaveMutation,
  useProcessingWatchedFolderRemuxScanDispatchEnqueueMutation,
} from "../../lib/processing/queries";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";

function canEdit(role: string | undefined): boolean {
  return role === "operator" || role === "admin";
}

/** One library's "Scan now". Each library has its own watched folder, so each scans on its own. */
function LibraryScanNow({
  library,
  canQueueManual,
}: {
  library: ProcessingLibrary;
  canQueueManual: boolean;
}) {
  const queueScan =
    useProcessingWatchedFolderRemuxScanDispatchEnqueueMutation();
  const watchedSet = Boolean(library.watched_folder.trim());
  const disabled = !canQueueManual || !watchedSet || queueScan.isPending;
  return (
    <tr data-testid="processing-schedules-library-scan">
      <th scope="row" className="mm-quiet-table__name">
        {library.name}
      </th>
      <td data-label="What it does">
        <span className="mm-quiet-table__sub">
          {PROCESSING_MEDIA_TYPE_LABELS[library.media_type]}. Checks this
          library&apos;s watched folder now and queues any ready files.
        </span>
        {!watchedSet ? (
          <span className="mt-1 block text-xs text-[var(--mm-status-warning-text)]">
            Save a watched folder for {library.name} in Libraries before running
            this scan.
          </span>
        ) : null}
        {queueScan.isError ? (
          <span
            className="mt-1 block text-xs text-[var(--mm-status-failed-text)]"
            role="alert"
          >
            {queueScan.error instanceof Error
              ? queueScan.error.message
              : `The scan for ${library.name} could not be queued.`}
          </span>
        ) : null}
        {queueScan.isSuccess ? (
          <span className="mt-1 block text-xs text-[var(--mm-text3)]">
            Queued scan job #{queueScan.data.job_id} for {library.name}.
          </span>
        ) : null}
      </td>
      <td data-label="Run">
        <button
          type="button"
          aria-label={`Scan ${library.name} now`}
          className={mmActionButtonClass({ variant: "secondary", disabled })}
          disabled={disabled}
          onClick={() =>
            queueScan.mutate({
              enqueue_remux_jobs: true,
              media_scope: library.media_type,
              library_id: library.id,
            })
          }
        >
          {queueScan.isPending ? "Starting scan..." : "Scan now"}
        </button>
      </td>
    </tr>
  );
}

/**
 * One watched-folder window. TV and Movies are two different forms of equal weight,
 * so they sit side by side as peers — there is no hero here to make one of them wider.
 */
function ScheduleWindow({
  headingId,
  heading,
  intro,
  idPrefix,
  switchId,
  hoursLimited,
  onHoursLimited,
  days,
  onDays,
  start,
  onStart,
  end,
  onEnd,
  disabled,
  saveDisabled,
  saveLabel,
  saving,
  onSave,
}: {
  headingId: string;
  heading: string;
  intro: string;
  idPrefix: string;
  switchId: string;
  hoursLimited: boolean;
  onHoursLimited: (next: boolean) => void;
  days: string;
  onDays: (next: string) => void;
  start: string;
  onStart: (next: string) => void;
  end: string;
  onEnd: (next: string) => void;
  disabled: boolean;
  saveDisabled: boolean;
  saveLabel: string;
  saving: boolean;
  onSave: () => void;
}) {
  return (
    <QuietSection headingId={headingId} heading={heading}>
      <p className="mm-quiet-note">{intro}</p>
      <div className="mt-5 space-y-4">
        <div>
          <span className="text-sm font-medium text-[var(--mm-text1)]">
            Schedule window
          </span>
          <p className="mt-1 text-xs text-[var(--mm-text3)]">
            {MM_SCHEDULE_TIME_WINDOW_HELPER}
          </p>
        </div>
        <MmOnOffSwitch
          id={switchId}
          label="Limit to these hours"
          enabled={hoursLimited}
          disabled={disabled}
          onChange={onHoursLimited}
        />
        <div className="space-y-2">
          <span className="text-sm font-medium text-[var(--mm-text1)]">
            Days
          </span>
          <MmScheduleDayChips
            scheduleDaysCsv={days}
            disabled={disabled}
            onChangeCsv={onDays}
          />
        </div>
        <MmScheduleTimeFields
          idPrefix={idPrefix}
          start={start}
          end={end}
          disabled={disabled}
          onStart={onStart}
          onEnd={onEnd}
        />
      </div>
      <div className={`${quietActionRowClass} mt-6`}>
        <button
          type="button"
          className={mmActionButtonClass({
            variant: "primary",
            disabled: saveDisabled,
          })}
          disabled={saveDisabled}
          onClick={onSave}
        >
          {saving ? "Saving…" : saveLabel}
        </button>
      </div>
    </QuietSection>
  );
}

export function ProcessingSchedulesSection() {
  const me = useMeQuery();
  const q = useProcessingOperatorSettingsQuery();
  const libraries = useProcessingLibrariesQuery();
  const saveTvSchedule = useProcessingOperatorSettingsSaveMutation();
  const saveMovieSchedule = useProcessingOperatorSettingsSaveMutation();
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

  if (q.isPending || libraries.isPending || me.isPending) {
    return <PageLoading label="Loading schedules" />;
  }
  if (q.isError || libraries.isError) {
    return (
      // Something broken, in the language's own shape for it: a sentence with the
      // interrupt marker, not a red box. Raw red-200 on a red-950 wash was also
      // unreadable in the light theme.
      <ul className="mm-interrupt" role="alert">
        <li className="mm-interrupt__item">
          <span className="mm-interrupt__text">
            <strong className="font-semibold">Could not load schedules.</strong>{" "}
            {isLikelyNetworkFailure(q.error ?? libraries.error)
              ? "Check that the Weir API is running."
              : isHttpErrorFromApi(q.error ?? libraries.error)
                ? "Sign in, then try again."
                : "Request failed."}
          </span>
        </li>
      </ul>
    );
  }
  if (!q.data || !libraries.data) {
    return null;
  }

  const canQueueManual = editable;
  const orderedLibraries = [...libraries.data].sort(
    (x, y) => x.display_order - y.display_order,
  );

  return (
    <div className="mm-quiet-stack" data-testid="processing-schedules-section">
      <div className="grid min-w-0 gap-10 xl:grid-cols-2 xl:gap-x-14">
        <ScheduleWindow
          headingId="processing-schedules-tv-heading"
          heading="TV watched-folder window"
          intro="Optional window for TV watched-folder checks from Libraries."
          idPrefix="processing-schedule-tv-window"
          switchId="processing-schedule-tv-hours-limited"
          hoursLimited={tvHoursLimited}
          onHoursLimited={setTvHoursLimited}
          days={tvDays}
          onDays={setTvDays}
          start={tvStart}
          onStart={setTvStart}
          end={tvEnd}
          onEnd={setTvEnd}
          disabled={!editable || saveTvSchedule.isPending}
          saveDisabled={!editable || !tvDirty || saveTvSchedule.isPending}
          saveLabel="Save TV schedule window"
          saving={saveTvSchedule.isPending}
          onSave={() =>
            saveTvSchedule.mutate({
              tv_schedule_enabled: q.data.tv_schedule_enabled,
              tv_schedule_hours_limited: tvHoursLimited,
              tv_schedule_days: tvDays,
              tv_schedule_start: tvStart,
              tv_schedule_end: tvEnd,
            })
          }
        />
        <ScheduleWindow
          headingId="processing-schedules-movies-heading"
          heading="Movies watched-folder window"
          intro="Optional window for Movies watched-folder checks from Libraries."
          idPrefix="processing-schedule-movie-window"
          switchId="processing-schedule-movie-hours-limited"
          hoursLimited={movieHoursLimited}
          onHoursLimited={setMovieHoursLimited}
          days={movieDays}
          onDays={setMovieDays}
          start={movieStart}
          onStart={setMovieStart}
          end={movieEnd}
          onEnd={setMovieEnd}
          disabled={!editable || saveMovieSchedule.isPending}
          saveDisabled={!editable || !movieDirty || saveMovieSchedule.isPending}
          saveLabel="Save Movies schedule window"
          saving={saveMovieSchedule.isPending}
          onSave={() =>
            saveMovieSchedule.mutate({
              movie_schedule_enabled: q.data.movie_schedule_enabled,
              movie_schedule_hours_limited: movieHoursLimited,
              movie_schedule_days: movieDays,
              movie_schedule_start: movieStart,
              movie_schedule_end: movieEnd,
            })
          }
        />
      </div>

      <QuietSection
        headingId="processing-schedules-run-now-heading"
        heading="Run now"
      >
        <p className="mm-quiet-note">
          Run a scan immediately without waiting for the next folder poll or
          window.
        </p>
        {orderedLibraries.length === 0 ? (
          <p className="mt-4 text-sm text-[var(--mm-text3)]">
            Add a library under Libraries to scan it here.
          </p>
        ) : (
          <div className="mm-quiet-table-wrap mt-5">
            <table className="mm-quiet-table">
              <thead>
                <tr>
                  <th scope="col">Library</th>
                  <th scope="col">What it does</th>
                  <th scope="col">Run</th>
                </tr>
              </thead>
              <tbody>
                {orderedLibraries.map((library) => (
                  <LibraryScanNow
                    key={library.id}
                    library={library}
                    canQueueManual={canQueueManual}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
        {!canQueueManual ? (
          <p className="mt-3 text-xs text-[var(--mm-text3)]">
            Operators and admins can queue manual scans.
          </p>
        ) : null}
      </QuietSection>

      {saveTvSchedule.isError ? (
        <p className="mm-status-text--failed text-sm" role="alert">
          {saveTvSchedule.error instanceof Error
            ? saveTvSchedule.error.message
            : "Save TV schedule window failed."}
        </p>
      ) : null}
      {saveMovieSchedule.isError ? (
        <p className="mm-status-text--failed text-sm" role="alert">
          {saveMovieSchedule.error instanceof Error
            ? saveMovieSchedule.error.message
            : "Save Movies schedule window failed."}
        </p>
      ) : null}
    </div>
  );
}
