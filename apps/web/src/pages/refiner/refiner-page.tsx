import { useState } from "react";
import { PageLoading } from "../../components/shared/page-loading";
import { isHttpErrorFromApi, isLikelyNetworkFailure } from "../../lib/api/error-guards";
import {
  isHandlerOkFinalizeFailedStatus,
  refinerJobStatusPrimaryLabel,
} from "../../lib/refiner/refiner-job-status-labels";
import type { RefinerInspectionFilter } from "../../lib/refiner/queries";
import { useRefinerJobsInspectionQuery } from "../../lib/refiner/queries";
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

const FILTER_OPTIONS: { value: RefinerInspectionFilter; label: string }[] = [
  { value: "terminal", label: "Terminal (default): completed, failed, handler_ok_finalize_failed" },
  { value: "handler_ok_finalize_failed", label: "Only handler_ok_finalize_failed" },
  { value: "failed", label: "Only failed" },
  { value: "completed", label: "Only completed" },
  { value: "pending", label: "Only pending" },
  { value: "leased", label: "Only leased" },
];

function JobRow({ job }: { job: RefinerJobInspectionRow }) {
  const emphasizeFinalize = isHandlerOkFinalizeFailedStatus(job.status);
  return (
    <tr
      data-testid="refiner-inspection-row"
      data-job-status={job.status}
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
    </tr>
  );
}

export function RefinerPage() {
  const [filter, setFilter] = useState<RefinerInspectionFilter>("terminal");
  const q = useRefinerJobsInspectionQuery(filter);

  if (q.isPending) {
    return <PageLoading label="Loading Refiner jobs" />;
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
        <p className="mm-page__subtitle">
          Read-only job queue inspection — no retries or recovery from here. Terminal view is the default;
          <code className="mm-dash-code"> handler_ok_finalize_failed</code> means the handler ran but completing the row
          in the database failed (not the same as ordinary <code className="mm-dash-code">failed</code>).
        </p>
      </header>

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
            {FILTER_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        {default_terminal_only ? (
          <p className="mm-card__body mm-card__body--tight text-sm text-[var(--mm-text3)]">
            Showing server default: terminal statuses only.
          </p>
        ) : (
          <p className="mm-card__body mm-card__body--tight text-sm text-[var(--mm-text3)]">
            Filtered to a single persisted status (see <code className="mm-dash-code">status</code> column).
          </p>
        )}
      </section>

      <section className="mm-card mm-dash-card overflow-x-auto" aria-labelledby="mm-refiner-jobs-heading">
        <h2 id="mm-refiner-jobs-heading" className="mm-card__title">
          Jobs
        </h2>
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
                  <th className="pb-2 pr-3 font-semibold">Job kind</th>
                  <th className="pb-2 pr-3 font-semibold">Dedupe key</th>
                  <th className="pb-2 pr-3 font-semibold">Attempts</th>
                  <th className="pb-2 pr-3 font-semibold">Updated</th>
                  <th className="pb-2 font-semibold">Last error</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--mm-border)]">
                {jobs.map((j) => (
                  <JobRow key={j.id} job={j} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
