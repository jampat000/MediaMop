import { useEffect, useState } from "react";
import type { UseMutationResult, UseQueryResult } from "@tanstack/react-query";
import { PageLoading } from "../../components/shared/page-loading";
import { isHttpErrorFromApi, isLikelyNetworkFailure } from "../../lib/api/error-guards";
import { useMeQuery } from "../../lib/auth/queries";
import {
  isHandlerOkFinalizeFailedStatus,
  refinerJobStatusPrimaryLabel,
} from "../../lib/refiner/refiner-job-status-labels";
import { REFINER_INSPECTION_FILTER_OPTIONS } from "../../lib/refiner/refiner-inspection-filter-labels";
import type { RefinerInspectionFilter } from "../../lib/refiner/queries";
import type { RefinerRuntimeVisibilityOut } from "../../lib/refiner/types";
import { manualCleanupEnqueueResultMessage } from "../../lib/refiner/refiner-manual-cleanup-enqueue-messages";
import { formatScheduleIntervalSeconds } from "../../lib/refiner/refiner-runtime-format";
import {
  useManualEnqueueRadarrCleanupDriveMutation,
  useManualEnqueueSonarrCleanupDriveMutation,
  useRecoverFinalizeFailureMutation,
  useRefinerJobsInspectionQuery,
  useRefinerRuntimeVisibilityQuery,
} from "../../lib/refiner/queries";
import {
  showManualCleanupDriveEnqueueControl,
  showRecoverFinalizeFailureControl,
} from "../../lib/refiner/refiner-recover-eligibility";
import type { RecoverFinalizeFailureResult } from "../../lib/refiner/refiner-recover-api";
import type { RefinerJobInspectionRow } from "../../lib/refiner/types";

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

function RefinerPageIntroSubtitle() {
  return (
    <p className="mm-page__subtitle">
      <span className="block">
        By default this page lists <strong className="font-semibold text-[var(--mm-text)]">finished</strong> jobs:
        completed, stopped after errors, or{" "}
        <strong className="font-semibold text-[var(--mm-text)]">needs manual finish</strong> — the work ran, but
        the app could not mark the row completed (not the same as a hard failure). Each row still shows the exact
        stored status under the plain label.
      </span>
      <span className="mt-2 block text-sm text-[var(--mm-text3)]">
        Admins and operators can use{" "}
        <strong className="font-semibold text-[var(--mm-text)]">Mark completed (manual)</strong> only on{" "}
        <strong>needs manual finish</strong> rows. It records an audit line and sets the row to completed without
        running the job again. Technical codes for reference:{" "}
        <code className="mm-dash-code">handler_ok_finalize_failed</code>,{" "}
        <code className="mm-dash-code">completed</code>, <code className="mm-dash-code">failed</code>.
      </span>
    </p>
  );
}

function RefinerManualCleanupEnqueuePanel({ enabled }: { enabled: boolean }) {
  const mRad = useManualEnqueueRadarrCleanupDriveMutation();
  const mSon = useManualEnqueueSonarrCleanupDriveMutation();

  if (!enabled) {
    return null;
  }

  const btnClass =
    "rounded border border-[var(--mm-border)] bg-[var(--mm-slate)] px-3 py-1.5 text-sm font-medium text-[var(--mm-text)] hover:bg-[var(--mm-card-bg)] disabled:opacity-50";

  return (
    <div
      className="border-t border-[var(--mm-border)] pt-4 mt-4"
      data-testid="refiner-manual-cleanup-enqueue"
    >
      <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">Queue cleanup drive</h3>
      <p className="mt-1 text-xs text-[var(--mm-text3)]">
        Adds or reuses one cleanup-drive queue entry per app. Nothing runs in this browser request, this does not show
        whether a worker picked the job up, and it does not mean the run finished.
      </p>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
        <button
          type="button"
          className={btnClass}
          data-testid="refiner-manual-enqueue-radarr"
          disabled={mRad.isPending || mSon.isPending}
          onClick={() => mRad.mutate()}
        >
          {mRad.isPending ? "Adding to queue…" : "Queue Radarr cleanup drive"}
        </button>
        <button
          type="button"
          className={btnClass}
          data-testid="refiner-manual-enqueue-sonarr"
          disabled={mRad.isPending || mSon.isPending}
          onClick={() => mSon.mutate()}
        >
          {mSon.isPending ? "Adding to queue…" : "Queue Sonarr cleanup drive"}
        </button>
      </div>
      {mRad.isError ? (
        <p className="mt-2 text-sm text-red-400" role="alert">
          {mRad.error instanceof Error ? mRad.error.message : "Radarr enqueue failed."}
        </p>
      ) : null}
      {mSon.isError ? (
        <p className="mt-2 text-sm text-red-400" role="alert">
          {mSon.error instanceof Error ? mSon.error.message : "Sonarr enqueue failed."}
        </p>
      ) : null}
      {mRad.isSuccess && mRad.data ? (
        <p className="mt-2 text-sm text-[var(--mm-text2)]" data-testid="refiner-manual-enqueue-radarr-result">
          Radarr: {manualCleanupEnqueueResultMessage(mRad.data)}
        </p>
      ) : null}
      {mSon.isSuccess && mSon.data ? (
        <p className="mt-2 text-sm text-[var(--mm-text2)]" data-testid="refiner-manual-enqueue-sonarr-result">
          Sonarr: {manualCleanupEnqueueResultMessage(mSon.data)}
        </p>
      ) : null}
    </div>
  );
}

function RefinerRuntimeVisibilitySection({
  rv,
  role,
}: {
  rv: UseQueryResult<RefinerRuntimeVisibilityOut, Error>;
  role: string | undefined;
}) {
  return (
    <section
      className="mm-card mm-dash-card mb-6"
      aria-labelledby="mm-refiner-runtime-heading"
      data-testid="refiner-runtime-visibility"
    >
      <h2 id="mm-refiner-runtime-heading" className="mm-card__title">
        Loaded settings (read-only)
      </h2>
      <p className="mm-card__body mm-card__body--tight text-sm text-[var(--mm-text3)]">
        From saved configuration when this loaded — not proof that background work is running.
      </p>
      {rv.isPending ? (
        <p className="mm-card__body text-sm text-[var(--mm-text3)]" data-testid="refiner-runtime-visibility-loading">
          Loading settings…
        </p>
      ) : rv.isError ? (
        <p className="mm-card__body text-sm text-red-400" data-testid="refiner-runtime-visibility-error" role="alert">
          {rv.error instanceof Error ? rv.error.message : "Could not load Refiner settings."}
        </p>
      ) : rv.data ? (
        <div className="mm-card__body mm-card__body--tight space-y-4 text-sm text-[var(--mm-text2)]">
          <div data-testid="refiner-runtime-worker-section">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">Workers</h3>
            <p className="mt-1">
              <span className="text-[var(--mm-text3)]">Worker slots (configured):</span>{" "}
              <code className="mm-dash-code" data-testid="refiner-runtime-worker-count">
                {rv.data.refiner_worker_count}
              </code>
            </p>
            <p className="mt-1 text-[var(--mm-text)]" data-testid="refiner-runtime-worker-summary">
              {rv.data.worker_mode_summary}
            </p>
          </div>
          <div
            className="border-t border-[var(--mm-border)] pt-3"
            data-testid="refiner-runtime-radarr-schedule"
          >
            <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
              Radarr cleanup-drive schedule
            </h3>
            <p className="mt-1">
              Scheduled:{" "}
              <span className="font-medium text-[var(--mm-text)]" data-testid="refiner-runtime-radarr-enabled">
                {yesNo(rv.data.refiner_radarr_cleanup_drive_schedule_enabled)}
              </span>
            </p>
            <p className="mt-1">
              Interval:{" "}
              <span data-testid="refiner-runtime-radarr-interval">
                {formatScheduleIntervalSeconds(rv.data.refiner_radarr_cleanup_drive_schedule_interval_seconds)}
              </span>
            </p>
          </div>
          <div
            className="border-t border-[var(--mm-border)] pt-3"
            data-testid="refiner-runtime-sonarr-schedule"
          >
            <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
              Sonarr cleanup-drive schedule
            </h3>
            <p className="mt-1">
              Scheduled:{" "}
              <span className="font-medium text-[var(--mm-text)]" data-testid="refiner-runtime-sonarr-enabled">
                {yesNo(rv.data.refiner_sonarr_cleanup_drive_schedule_enabled)}
              </span>
            </p>
            <p className="mt-1">
              Interval:{" "}
              <span data-testid="refiner-runtime-sonarr-interval">
                {formatScheduleIntervalSeconds(rv.data.refiner_sonarr_cleanup_drive_schedule_interval_seconds)}
              </span>
            </p>
          </div>
          <p className="border-t border-[var(--mm-border)] pt-3 text-xs text-[var(--mm-text3)]">
            {rv.data.visibility_note}
          </p>
          <RefinerManualCleanupEnqueuePanel enabled={showManualCleanupDriveEnqueueControl(role)} />
        </div>
      ) : null}
    </section>
  );
}

function JobRow({
  job,
  role,
  recoverMutation,
}: {
  job: RefinerJobInspectionRow;
  role: string | undefined;
  recoverMutation: UseMutationResult<RecoverFinalizeFailureResult, Error, number, unknown>;
}) {
  const emphasizeFinalize = isHandlerOkFinalizeFailedStatus(job.status);
  const showRecover = showRecoverFinalizeFailureControl(role, job.status);
  return (
    <tr
      data-testid="refiner-inspection-row"
      data-job-status={job.status}
      data-recover-visible={showRecover ? "true" : "false"}
      className={
        emphasizeFinalize
          ? "border-l-2 border-l-[var(--mm-accent)] bg-[rgba(212,175,55,0.06)]"
          : undefined
      }
    >
      <td className="mm-refiner-inspection__cell align-top py-2 pr-3">
        <div className="font-medium text-[var(--mm-text)]" data-testid="refiner-inspection-status-label">
          {refinerJobStatusPrimaryLabel(job.status)}
        </div>
        <code className="mm-dash-code mt-0.5 block text-xs text-[var(--mm-text3)]">{job.status}</code>
      </td>
      <td className="mm-refiner-inspection__cell align-top py-2 pr-3 font-mono text-xs text-[var(--mm-text2)]">
        {job.job_kind}
      </td>
      <td className="mm-refiner-inspection__cell align-top py-2 pr-3 font-mono text-xs text-[var(--mm-text2)] break-all">
        {job.dedupe_key}
      </td>
      <td className="mm-refiner-inspection__cell align-top py-2 pr-3 text-sm text-[var(--mm-text2)] whitespace-nowrap">
        {job.attempt_count} / {job.max_attempts}
      </td>
      <td className="mm-refiner-inspection__cell align-top py-2 pr-3 text-sm text-[var(--mm-text2)] whitespace-nowrap">
        {formatUpdated(job.updated_at)}
      </td>
      <td className="mm-refiner-inspection__cell align-top py-2 text-sm text-[var(--mm-text3)] break-words max-w-[min(28rem,40vw)]">
        {job.last_error ? <span className="font-mono text-xs">{job.last_error}</span> : "—"}
      </td>
      <td className="mm-refiner-inspection__cell align-top py-2 pr-0">
        {showRecover ? (
          <button
            type="button"
            data-testid={`refiner-recover-finalize-${job.id}`}
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

export function RefinerPage() {
  const [filter, setFilter] = useState<RefinerInspectionFilter>("terminal");
  const me = useMeQuery();
  const rv = useRefinerRuntimeVisibilityQuery();
  const q = useRefinerJobsInspectionQuery(filter);
  const recoverMutation = useRecoverFinalizeFailureMutation();

  useEffect(() => {
    recoverMutation.reset();
    // Only clear stale mutation UI when the inspection filter changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- recoverMutation is stable from useMutation
  }, [filter]);

  if (q.isPending) {
    return (
      <div className="mm-page">
        <header className="mm-page__intro">
          <p className="mm-page__eyebrow">MediaMop</p>
          <h1 className="mm-page__title">Refiner</h1>
          <RefinerPageIntroSubtitle />
        </header>
        <RefinerRuntimeVisibilitySection rv={rv} role={me.data?.role} />
        <PageLoading label="Loading Refiner jobs" />
      </div>
    );
  }

  if (q.isError) {
    const err = q.error;
    return (
      <div className="mm-page">
        <header className="mm-page__intro">
          <p className="mm-page__eyebrow">MediaMop</p>
          <h1 className="mm-page__title">Refiner</h1>
          <p className="mm-page__lead">
            {isLikelyNetworkFailure(err)
              ? "Could not reach the MediaMop API. Check that the backend is running."
              : isHttpErrorFromApi(err)
                ? "The server refused this request. Sign in again or check API logs."
                : "Could not load Refiner job inspection."}
          </p>
        </header>
        <RefinerRuntimeVisibilitySection rv={rv} role={me.data?.role} />
        {err instanceof Error ? (
          <p className="mm-page__lead font-mono text-sm text-[var(--mm-text3)]">{err.message}</p>
        ) : null}
      </div>
    );
  }

  const { jobs, default_terminal_only } = q.data;
  const isEmpty = jobs.length === 0;

  return (
    <div className="mm-page">
      <header className="mm-page__intro">
        <p className="mm-page__eyebrow">MediaMop</p>
        <h1 className="mm-page__title">Refiner</h1>
        <RefinerPageIntroSubtitle />
      </header>

      <RefinerRuntimeVisibilitySection rv={rv} role={me.data?.role} />

      <section className="mm-card mm-dash-card mb-6" aria-labelledby="mm-refiner-filter-heading">
        <h2 id="mm-refiner-filter-heading" className="mm-card__title">
          Filter
        </h2>
        <label className="mm-card__body mm-card__body--tight block">
          <span className="sr-only">Status filter</span>
          <select
            data-testid="refiner-inspection-status-filter"
            className="mm-refiner-inspection__select mt-1 w-full max-w-xl rounded border border-[var(--mm-border)] bg-[var(--mm-slate)] px-2 py-1.5 text-sm text-[var(--mm-text)]"
            value={filter}
            onChange={(e) => setFilter(e.target.value as RefinerInspectionFilter)}
          >
            {REFINER_INSPECTION_FILTER_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        {default_terminal_only ? (
          <p className="mm-card__body mm-card__body--tight text-sm text-[var(--mm-text3)]">
            Showing the server default: finished jobs only.
          </p>
        ) : (
          <p className="mm-card__body mm-card__body--tight text-sm text-[var(--mm-text3)]">
            Filtered to a single stored status — see the Status column for the exact value.
          </p>
        )}
      </section>

      <section className="mm-card mm-dash-card overflow-x-auto" aria-labelledby="mm-refiner-jobs-heading">
        <h2 id="mm-refiner-jobs-heading" className="mm-card__title">
          Jobs
        </h2>
        {recoverMutation.isError ? (
          <p className="mm-card__body text-sm text-red-400" role="alert">
            {recoverMutation.error instanceof Error
              ? recoverMutation.error.message
              : "Could not apply manual completion."}
          </p>
        ) : null}
        {isEmpty ? (
          <p className="mm-card__body" data-testid="refiner-inspection-empty">
            No rows match this view.
          </p>
        ) : (
          <div className="mm-card__body mm-card__body--tight">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-[var(--mm-border)] text-xs uppercase tracking-wide text-[var(--mm-text3)]">
                  <th className="pb-2 pr-3 font-semibold">Status</th>
                  <th className="pb-2 pr-3 font-semibold">Job type</th>
                  <th className="pb-2 pr-3 font-semibold">Identity key</th>
                  <th className="pb-2 pr-3 font-semibold">Attempts</th>
                  <th className="pb-2 pr-3 font-semibold">Updated</th>
                  <th className="pb-2 pr-3 font-semibold">Last error</th>
                  <th className="pb-2 font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--mm-border)]">
                {jobs.map((j) => (
                  <JobRow
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
