import { useEffect, useState } from "react";
import type { UseMutationResult, UseQueryResult } from "@tanstack/react-query";
import { PageLoading } from "../../components/shared/page-loading";
import { isHttpErrorFromApi, isLikelyNetworkFailure } from "../../lib/api/error-guards";
import { useMeQuery } from "../../lib/auth/queries";
import { failedImportManualQueuePassResultMessage } from "../../lib/fetcher/failed-imports/enqueue-messages";
import {
  showFailedImportManualQueuePassControl,
  showFailedImportRecoverControl,
} from "../../lib/fetcher/failed-imports/eligibility";
import { FetcherFailedImportsCleanupPolicySection } from "./fetcher-failed-imports-cleanup-policy";
import {
  fetcherJobDedupeKeyOperatorLabel,
  fetcherJobKindOperatorLabel,
} from "../../lib/fetcher/fetcher-job-operator-labels";
import { FETCHER_JOBS_INSPECTION_FILTER_OPTIONS } from "../../lib/fetcher/jobs-inspection/filter-labels";
import type { FetcherJobsInspectionFilter } from "../../lib/fetcher/jobs-inspection/queries";
import { useFetcherJobsInspectionQuery } from "../../lib/fetcher/jobs-inspection/queries";
import {
  useFailedImportFetcherSettingsQuery,
  useFailedImportRadarrEnqueueMutation,
  useFailedImportRecoverMutation,
  useFailedImportSonarrEnqueueMutation,
} from "../../lib/fetcher/failed-imports/queries";
import { formatScheduleIntervalSeconds } from "../../lib/fetcher/failed-imports/schedule-format";
import {
  failedImportTaskStatusPrimaryLabel,
  isHandlerOkFinalizeFailedStatus,
} from "../../lib/fetcher/failed-imports/task-status-labels";
import type { FailedImportFetcherSettingsOut } from "../../lib/fetcher/failed-imports/types";
import type { FetcherJobInspectionRow } from "../../lib/fetcher/jobs-inspection/types";
import {
  FETCHER_FI_FILTER_DEFAULT_HELP,
  FETCHER_FI_FILTER_SINGLE_STATUS_HELP,
  FETCHER_FI_LIST_EMPTY,
  FETCHER_FI_MANUAL_BTN_MOVIES,
  FETCHER_FI_MANUAL_BTN_TV,
  FETCHER_FI_MANUAL_ERR_MOVIES,
  FETCHER_FI_MANUAL_ERR_TV,
  FETCHER_FI_MANUAL_PENDING,
  FETCHER_FI_MANUAL_RESULT_MOVIES_PREFIX,
  FETCHER_FI_MANUAL_RESULT_TV_PREFIX,
  FETCHER_FI_MANUAL_SECTION_BODY,
  FETCHER_FI_MANUAL_SECTION_TITLE,
  FETCHER_FI_PAGE_ERR_LOAD_TASKS,
  FETCHER_FI_PAGE_LOADING_TASKS,
  FETCHER_FI_RUNTIME_CARD_SUBTITLE,
  FETCHER_FI_RUNTIME_CARD_TITLE,
  FETCHER_FI_RUNTIME_WORKER_COUNT_LABEL,
  FETCHER_FI_RUNTIME_WORKERS_HEADING,
  FETCHER_FI_SCHEDULE_MOVIES_HEADING,
  FETCHER_FI_SCHEDULE_TV_HEADING,
  FETCHER_FI_SECTION_INTRO_PRIMARY,
  FETCHER_FI_TASKS_SECTION_TITLE,
  FETCHER_FI_TABLE_COL_STABLE_KEY,
  FETCHER_FI_TABLE_COL_WORK_TYPE,
  FETCHER_FI_TECHNICAL_SUMMARY_LABEL,
} from "../../lib/fetcher/failed-imports/user-copy";
import type { FailedImportRecoverFinalizeResult } from "../../lib/fetcher/failed-imports/recover-api";

function formatUpdated(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) {
      return iso;
    }
    return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(d);
  } catch {
    return iso;
  }
}

function yesNo(value: boolean): string {
  return value ? "Yes" : "No";
}

function FetcherFailedImportsIntroSubtitle() {
  return (
    <div className="mm-page__subtitle space-y-2">
      <p>{FETCHER_FI_SECTION_INTRO_PRIMARY}</p>
      <details className="text-sm text-[var(--mm-text3)]">
        <summary className="cursor-pointer text-[var(--mm-text2)] select-none">
          {FETCHER_FI_TECHNICAL_SUMMARY_LABEL}
        </summary>
        <p className="mt-2">
          Default view: <strong>finished</strong> outcomes—completed, stopped with errors, or{" "}
          <strong>needs manual finish</strong>. <strong>Mark completed (manual)</strong> only on the last; it does not
          rerun the sweep.
        </p>
        <p className="mt-2 font-mono text-xs text-[var(--mm-text3)]">
          handler_ok_finalize_failed · completed · failed
        </p>
      </details>
    </div>
  );
}

function FetcherFailedImportsManualQueuePassPanel({ enabled }: { enabled: boolean }) {
  const mRad = useFailedImportRadarrEnqueueMutation();
  const mSon = useFailedImportSonarrEnqueueMutation();

  if (!enabled) {
    return null;
  }

  const btnClass =
    "rounded border border-[var(--mm-border)] bg-[var(--mm-slate)] px-3 py-1.5 text-sm font-medium text-[var(--mm-text)] hover:bg-[var(--mm-card-bg)] disabled:opacity-50";

  return (
    <div
      className="border-t border-[var(--mm-border)] pt-4 mt-4"
      data-testid="fetcher-failed-imports-manual-queue-pass"
    >
      <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
        {FETCHER_FI_MANUAL_SECTION_TITLE}
      </h3>
      <p className="mt-1 text-xs text-[var(--mm-text3)]">{FETCHER_FI_MANUAL_SECTION_BODY}</p>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
        <button
          type="button"
          className={btnClass}
          data-testid="fetcher-failed-imports-queue-pass-radarr"
          disabled={mRad.isPending || mSon.isPending}
          onClick={() => mRad.mutate()}
        >
          {mRad.isPending ? FETCHER_FI_MANUAL_PENDING : FETCHER_FI_MANUAL_BTN_MOVIES}
        </button>
        <button
          type="button"
          className={btnClass}
          data-testid="fetcher-failed-imports-queue-pass-sonarr"
          disabled={mRad.isPending || mSon.isPending}
          onClick={() => mSon.mutate()}
        >
          {mSon.isPending ? FETCHER_FI_MANUAL_PENDING : FETCHER_FI_MANUAL_BTN_TV}
        </button>
      </div>
      {mRad.isError ? (
        <p className="mt-2 text-sm text-red-400" role="alert">
          {mRad.error instanceof Error ? mRad.error.message : FETCHER_FI_MANUAL_ERR_MOVIES}
        </p>
      ) : null}
      {mSon.isError ? (
        <p className="mt-2 text-sm text-red-400" role="alert">
          {mSon.error instanceof Error ? mSon.error.message : FETCHER_FI_MANUAL_ERR_TV}
        </p>
      ) : null}
      {mRad.isSuccess && mRad.data ? (
        <p className="mt-2 text-sm text-[var(--mm-text2)]" data-testid="fetcher-failed-imports-queue-pass-radarr-result">
          {FETCHER_FI_MANUAL_RESULT_MOVIES_PREFIX} {failedImportManualQueuePassResultMessage(mRad.data)}
        </p>
      ) : null}
      {mSon.isSuccess && mSon.data ? (
        <p className="mt-2 text-sm text-[var(--mm-text2)]" data-testid="fetcher-failed-imports-queue-pass-sonarr-result">
          {FETCHER_FI_MANUAL_RESULT_TV_PREFIX} {failedImportManualQueuePassResultMessage(mSon.data)}
        </p>
      ) : null}
    </div>
  );
}

function FetcherFailedImportsSettingsSection({
  rv,
  role,
}: {
  rv: UseQueryResult<FailedImportFetcherSettingsOut, Error>;
  role: string | undefined;
}) {
  return (
    <section
      className="mm-card mm-dash-card mm-fetcher-module-surface mb-6"
      aria-labelledby="mm-fetcher-fi-settings-heading"
      data-testid="fetcher-failed-imports-settings"
    >
      <h2 id="mm-fetcher-fi-settings-heading" className="mm-card__title">
        {FETCHER_FI_RUNTIME_CARD_TITLE}
      </h2>
      <p className="mm-card__body mm-card__body--tight text-sm text-[var(--mm-text3)]">
        {FETCHER_FI_RUNTIME_CARD_SUBTITLE}
      </p>
      {rv.isPending ? (
        <p className="mm-card__body text-sm text-[var(--mm-text3)]" data-testid="fetcher-failed-imports-settings-loading">
          Loading settings…
        </p>
      ) : rv.isError ? (
        <p className="mm-card__body text-sm text-red-400" data-testid="fetcher-failed-imports-settings-error" role="alert">
          {rv.error instanceof Error ? rv.error.message : "Could not load automation settings."}
        </p>
      ) : rv.data ? (
        <div className="mm-card__body mm-card__body--tight space-y-4 text-sm text-[var(--mm-text2)]">
          <div data-testid="fetcher-failed-imports-runners">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
              {FETCHER_FI_RUNTIME_WORKERS_HEADING}
            </h3>
            <p className="mt-1">
              <span className="text-[var(--mm-text3)]">{FETCHER_FI_RUNTIME_WORKER_COUNT_LABEL}</span>{" "}
              <code className="mm-dash-code" data-testid="fetcher-failed-imports-worker-count">
                {rv.data.background_job_worker_count}
              </code>
            </p>
            <p className="mt-1 text-[var(--mm-text)]" data-testid="fetcher-failed-imports-worker-summary">
              {rv.data.worker_mode_summary}
            </p>
          </div>
          <div className="border-t border-[var(--mm-border)] pt-3" data-testid="fetcher-failed-imports-radarr-schedule">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
              {FETCHER_FI_SCHEDULE_MOVIES_HEADING}
            </h3>
            <p className="mt-1">
              Scheduled:{" "}
              <span className="font-medium text-[var(--mm-text)]" data-testid="fetcher-failed-imports-radarr-enabled">
                {yesNo(rv.data.failed_import_radarr_cleanup_drive_schedule_enabled)}
              </span>
            </p>
            <p className="mt-1">
              Interval:{" "}
              <span data-testid="fetcher-failed-imports-radarr-interval">
                {formatScheduleIntervalSeconds(rv.data.failed_import_radarr_cleanup_drive_schedule_interval_seconds)}
              </span>
            </p>
          </div>
          <div className="border-t border-[var(--mm-border)] pt-3" data-testid="fetcher-failed-imports-sonarr-schedule">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
              {FETCHER_FI_SCHEDULE_TV_HEADING}
            </h3>
            <p className="mt-1">
              Scheduled:{" "}
              <span className="font-medium text-[var(--mm-text)]" data-testid="fetcher-failed-imports-sonarr-enabled">
                {yesNo(rv.data.failed_import_sonarr_cleanup_drive_schedule_enabled)}
              </span>
            </p>
            <p className="mt-1">
              Interval:{" "}
              <span data-testid="fetcher-failed-imports-sonarr-interval">
                {formatScheduleIntervalSeconds(rv.data.failed_import_sonarr_cleanup_drive_schedule_interval_seconds)}
              </span>
            </p>
          </div>
          <p className="border-t border-[var(--mm-border)] pt-3 text-xs text-[var(--mm-text3)]">
            {rv.data.visibility_note}
          </p>
          <FetcherFailedImportsManualQueuePassPanel enabled={showFailedImportManualQueuePassControl(role)} />
        </div>
      ) : null}
    </section>
  );
}

function TaskRow({
  job,
  role,
  recoverMutation,
}: {
  job: FetcherJobInspectionRow;
  role: string | undefined;
  recoverMutation: UseMutationResult<FailedImportRecoverFinalizeResult, Error, number, unknown>;
}) {
  const emphasizeFinalize = isHandlerOkFinalizeFailedStatus(job.status);
  const showRecover = showFailedImportRecoverControl(role, job.status);
  return (
    <tr
      data-testid="fetcher-jobs-inspection-row"
      data-job-status={job.status}
      data-recover-visible={showRecover ? "true" : "false"}
      className={
        emphasizeFinalize
          ? "border-l-2 border-l-[var(--mm-accent)] bg-[rgba(212,175,55,0.06)]"
          : undefined
      }
    >
      <td className="mm-fetcher-fi-inspection__cell align-top py-2 pr-3">
        <div className="font-medium text-[var(--mm-text)]" data-testid="fetcher-failed-imports-status-label">
          {failedImportTaskStatusPrimaryLabel(job.status)}
        </div>
        <code className="mm-dash-code mt-0.5 block text-xs text-[var(--mm-text3)]">{job.status}</code>
      </td>
      <td className="mm-fetcher-fi-inspection__cell align-top py-2 pr-3 text-sm text-[var(--mm-text)]">
        <span data-testid="fetcher-jobs-inspection-job-kind-label">
          {fetcherJobKindOperatorLabel(job.job_kind)}
        </span>
        <span className="sr-only"> Technical job kind: {job.job_kind}.</span>
      </td>
      <td className="mm-fetcher-fi-inspection__cell align-top py-2 pr-3 text-sm text-[var(--mm-text)] break-words">
        <span data-testid="fetcher-jobs-inspection-stable-key-label">
          {fetcherJobDedupeKeyOperatorLabel(job.dedupe_key, job.job_kind)}
        </span>
        <span className="sr-only"> Technical stable key: {job.dedupe_key}.</span>
      </td>
      <td className="mm-fetcher-fi-inspection__cell align-top py-2 pr-3 text-sm text-[var(--mm-text2)] whitespace-nowrap">
        {job.attempt_count} / {job.max_attempts}
      </td>
      <td className="mm-fetcher-fi-inspection__cell align-top py-2 pr-3 text-sm text-[var(--mm-text2)] whitespace-nowrap">
        {formatUpdated(job.updated_at)}
      </td>
      <td className="mm-fetcher-fi-inspection__cell align-top py-2 text-sm text-[var(--mm-text3)] break-words max-w-[min(28rem,40vw)]">
        {job.last_error ? <span className="font-mono text-xs">{job.last_error}</span> : "—"}
      </td>
      <td className="mm-fetcher-fi-inspection__cell align-top py-2 pr-0">
        {showRecover ? (
          <button
            type="button"
            data-testid={`fetcher-failed-imports-recover-${job.id}`}
            className="rounded border border-[var(--mm-border)] bg-[var(--mm-slate)] px-2 py-1 text-xs font-medium text-[var(--mm-text)] hover:bg-[var(--mm-card-bg)] disabled:opacity-50"
            disabled={recoverMutation.isPending}
            onClick={() => recoverMutation.mutate(job.id)}
          >
            Mark completed (manual)
          </button>
        ) : (
          <span className="text-xs text-[var(--mm-text3)]">—</span>
        )}
      </td>
    </tr>
  );
}

/** Fetcher page section: failed-import automation plus persisted ``fetcher_jobs`` history (all kinds on this lane). */
export function FetcherFailedImportsWorkspace() {
  const [filter, setFilter] = useState<FetcherJobsInspectionFilter>("terminal");
  const me = useMeQuery();
  const rv = useFailedImportFetcherSettingsQuery();
  const q = useFetcherJobsInspectionQuery(filter);
  const recoverMutation = useFailedImportRecoverMutation();

  useEffect(() => {
    recoverMutation.reset();
    // Only clear stale mutation UI when the inspection filter changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- recoverMutation is stable from useMutation
  }, [filter]);

  if (q.isPending) {
    return (
      <div data-testid="fetcher-failed-imports-workspace">
        <header className="mm-page__intro">
          <h2 className="mm-page__title text-xl sm:text-2xl">Failed imports</h2>
          <FetcherFailedImportsIntroSubtitle />
        </header>
        <FetcherFailedImportsSettingsSection rv={rv} role={me.data?.role} />
        <FetcherFailedImportsCleanupPolicySection role={me.data?.role} />
        <PageLoading label={FETCHER_FI_PAGE_LOADING_TASKS} />
      </div>
    );
  }

  if (q.isError) {
    const err = q.error;
    return (
      <div data-testid="fetcher-failed-imports-workspace">
        <header className="mm-page__intro">
          <h2 className="mm-page__title text-xl sm:text-2xl">Failed imports</h2>
          <FetcherFailedImportsIntroSubtitle />
          <p className="mm-page__lead">
            {isLikelyNetworkFailure(err)
              ? "Could not reach the MediaMop API. Check that the backend is running."
              : isHttpErrorFromApi(err)
                ? "The server refused this request. Sign in again or check API logs."
                : FETCHER_FI_PAGE_ERR_LOAD_TASKS}
          </p>
        </header>
        <FetcherFailedImportsSettingsSection rv={rv} role={me.data?.role} />
        <FetcherFailedImportsCleanupPolicySection role={me.data?.role} />
        {err instanceof Error ? (
          <p className="mm-page__lead font-mono text-sm text-[var(--mm-text3)]">{err.message}</p>
        ) : null}
      </div>
    );
  }

  const { jobs, default_terminal_only } = q.data;
  const isEmpty = jobs.length === 0;

  return (
    <div data-testid="fetcher-failed-imports-workspace">
      <header className="mm-page__intro">
        <h2 className="mm-page__title text-xl sm:text-2xl">Failed imports</h2>
        <FetcherFailedImportsIntroSubtitle />
      </header>

      <FetcherFailedImportsSettingsSection rv={rv} role={me.data?.role} />

      <FetcherFailedImportsCleanupPolicySection role={me.data?.role} />

      <section
        className="mm-card mm-dash-card mm-fetcher-module-surface mb-6"
        aria-labelledby="mm-fetcher-fi-filter-heading"
      >
        <h2 id="mm-fetcher-fi-filter-heading" className="mm-card__title">
          View
        </h2>
        <label className="mm-card__body mm-card__body--tight block">
          <span className="sr-only">Status filter</span>
          <select
            data-testid="fetcher-failed-imports-status-filter"
            className="mm-fetcher-fi-inspection__select mt-1 w-full max-w-xl rounded border border-[var(--mm-border)] bg-[var(--mm-slate)] px-2 py-1.5 text-sm text-[var(--mm-text)]"
            value={filter}
            onChange={(e) => setFilter(e.target.value as FetcherJobsInspectionFilter)}
          >
            {FETCHER_JOBS_INSPECTION_FILTER_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        {default_terminal_only ? (
          <p className="mm-card__body mm-card__body--tight text-sm text-[var(--mm-text3)]">
            {FETCHER_FI_FILTER_DEFAULT_HELP}
          </p>
        ) : (
          <p className="mm-card__body mm-card__body--tight text-sm text-[var(--mm-text3)]">
            {FETCHER_FI_FILTER_SINGLE_STATUS_HELP}
          </p>
        )}
      </section>

      <section
        className="mm-card mm-dash-card mm-fetcher-module-surface overflow-x-auto"
        aria-labelledby="mm-fetcher-fi-tasks-heading"
      >
        <h2 id="mm-fetcher-fi-tasks-heading" className="mm-card__title">
          {FETCHER_FI_TASKS_SECTION_TITLE}
        </h2>
        {recoverMutation.isError ? (
          <p className="mm-card__body text-sm text-red-400" role="alert">
            {recoverMutation.error instanceof Error
              ? recoverMutation.error.message
              : "Could not apply manual completion."}
          </p>
        ) : null}
        {isEmpty ? (
          <p className="mm-card__body" data-testid="fetcher-jobs-inspection-empty">
            {FETCHER_FI_LIST_EMPTY}
          </p>
        ) : (
          <div className="mm-card__body mm-card__body--tight">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-[var(--mm-border)] text-xs uppercase tracking-wide text-[var(--mm-text3)]">
                  <th className="pb-2 pr-3 font-semibold">Status</th>
                  <th className="pb-2 pr-3 font-semibold">{FETCHER_FI_TABLE_COL_WORK_TYPE}</th>
                  <th className="pb-2 pr-3 font-semibold">{FETCHER_FI_TABLE_COL_STABLE_KEY}</th>
                  <th className="pb-2 pr-3 font-semibold">Retries</th>
                  <th className="pb-2 pr-3 font-semibold">Last change</th>
                  <th className="pb-2 pr-3 font-semibold">Details</th>
                  <th className="pb-2 font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--mm-border)]">
                {jobs.map((j) => (
                  <TaskRow
                    key={j.id}
                    job={j}
                    role={me.data?.role}
                    recoverMutation={recoverMutation}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
