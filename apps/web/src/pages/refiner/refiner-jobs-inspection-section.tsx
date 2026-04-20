import { useId, useState } from "react";
import { PageLoading } from "../../components/shared/page-loading";
import { isHttpErrorFromApi, isLikelyNetworkFailure } from "../../lib/api/error-guards";
import { useMeQuery } from "../../lib/auth/queries";
import type { RefinerJobsInspectionFilter } from "../../lib/refiner/jobs-inspection/queries";
import {
  useRefinerJobCancelPendingMutation,
  useRefinerJobsInspectionQuery,
} from "../../lib/refiner/jobs-inspection/queries";
import type { RefinerJobInspectionRow } from "../../lib/refiner/jobs-inspection/types";
import { MmListboxPicker } from "../../components/ui/mm-listbox-picker";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";

function canCancelRefinerJobs(role: string | undefined): boolean {
  return role === "operator" || role === "admin";
}

function statusLabel(status: string): string {
  if (status === "handler_ok_finalize_failed") {
    return "finalize failed";
  }
  return status;
}

const REFINER_JOBS_INSPECTION_FILTER_OPTIONS: { value: RefinerJobsInspectionFilter; label: string }[] = [
  { value: "recent", label: "Recent (all statuses, newest first)" },
  { value: "pending", label: "Pending only" },
  { value: "leased", label: "Leased only" },
  { value: "terminal", label: "Terminal (completed, failed, finalize-failed)" },
  { value: "cancelled", label: "Cancelled only" },
  { value: "completed", label: "Completed only" },
  { value: "failed", label: "Failed only" },
  { value: "handler_ok_finalize_failed", label: "Finalize-failed only" },
];

/** Read ``refiner_jobs`` lifecycle here; finished outcomes stay on Activity. */
export function RefinerJobsInspectionSection() {
  const me = useMeQuery();
  const filterLabelId = useId();
  const [filter, setFilter] = useState<RefinerJobsInspectionFilter>("recent");
  const q = useRefinerJobsInspectionQuery(filter);
  const cancel = useRefinerJobCancelPendingMutation();
  const canCancel = canCancelRefinerJobs(me.data?.role);

  if (q.isPending || me.isPending) {
    return <PageLoading label="Loading Refiner jobs" />;
  }
  if (q.isError) {
    return (
      <div
        className="mm-fetcher-module-surface w-full min-w-0 rounded border border-red-900/40 bg-red-950/20 p-4 text-sm text-red-200"
        data-testid="refiner-jobs-inspection-error"
        role="alert"
      >
        <p className="font-semibold">Could not load Refiner jobs</p>
        <p className="mt-1">
          {isLikelyNetworkFailure(q.error)
            ? "Check that the MediaMop API is running."
            : isHttpErrorFromApi(q.error)
              ? "Sign in, then try again."
              : "Request failed."}
        </p>
      </div>
    );
  }

  const jobs = q.data?.jobs ?? [];

  return (
    <section
      className="mm-fetcher-module-surface w-full min-w-0 rounded border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-6 text-sm leading-relaxed text-[var(--mm-text2)] sm:p-7"
      aria-labelledby="refiner-jobs-inspection-heading"
      data-testid="refiner-jobs-inspection-section"
    >
      <h2 id="refiner-jobs-inspection-heading" className="text-base font-semibold text-[var(--mm-text)]">
        Jobs
      </h2>
      <p className="mt-2 max-w-3xl text-[var(--mm-text3)]">
        Pending, running, and finished Refiner work on this server. When a job completes, check{" "}
        <strong className="text-[var(--mm-text)]">Activity</strong> for the outcome.
      </p>
      <p className="mt-2 max-w-3xl text-xs text-[var(--mm-text3)]">
        Operators and admins can <strong className="text-[var(--mm-text)]">Cancel pending</strong> only — not work that is
        already running or finished.
      </p>

      <div className="mt-7 flex flex-col gap-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-4 sm:flex-row sm:items-end sm:justify-between sm:px-5 sm:py-4">
        <label className="block min-w-0 flex-1">
          <span id={filterLabelId} className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
            Show jobs
          </span>
          <MmListboxPicker
            className="mt-2 max-w-xl"
            data-testid="refiner-jobs-inspection-filter"
            ariaLabelledBy={filterLabelId}
            placeholder="Select filter"
            options={REFINER_JOBS_INSPECTION_FILTER_OPTIONS}
            value={filter}
            onChange={(v) => setFilter(v as RefinerJobsInspectionFilter)}
          />
        </label>
        <p className="w-full text-left text-[0.7rem] leading-snug text-[var(--mm-text3)] sm:w-auto sm:max-w-[14rem] sm:text-right">
          {jobs.length} row{jobs.length === 1 ? "" : "s"} for this filter.
        </p>
      </div>

      {cancel.isError ? (
        <p className="mt-3 text-sm text-red-300" role="alert" data-testid="refiner-jobs-inspection-cancel-error">
          {cancel.error instanceof Error ? cancel.error.message : "Cancel failed."}
        </p>
      ) : null}

      {jobs.length === 0 ? (
        <div
          className="mt-6 rounded-md border border-[var(--mm-border)] bg-black/10 px-5 py-8 text-center sm:px-8"
          data-testid="refiner-jobs-inspection-empty"
        >
          <p className="text-sm font-semibold text-[var(--mm-text1)]">No jobs match this view</p>
          <p className="mx-auto mt-2 max-w-md text-xs leading-relaxed text-[var(--mm-text3)]">
            Nothing matches this filter yet. Try <strong className="text-[var(--mm-text2)]">Recent (all statuses)</strong>{" "}
            for the latest rows, or check <strong className="text-[var(--mm-text2)]">Activity</strong> after a run finishes.
          </p>
        </div>
      ) : (
        <div className="mt-6 w-full min-w-0 overflow-x-auto rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-1 sm:p-2">
          <table className="w-full min-w-[38rem] border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-[var(--mm-border)] bg-black/10 text-[var(--mm-text3)]">
                <th className="rounded-tl-md py-2.5 pr-2 pl-2 font-semibold">ID</th>
                <th className="py-2 pr-2 font-semibold">Status</th>
                <th className="py-2 pr-2 font-semibold">Kind</th>
                <th className="py-2 pr-2 font-semibold">Updated</th>
                <th className="py-2 pr-2 font-semibold">Lease</th>
                <th className="py-2 pr-2 font-semibold">Dedupe</th>
                <th className="py-2 pr-0 font-semibold"> </th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <RefinerJobRow key={j.id} job={j} canCancel={canCancel} cancelMutation={cancel} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function RefinerJobRow({
  job,
  canCancel,
  cancelMutation,
}: {
  job: RefinerJobInspectionRow;
  canCancel: boolean;
  cancelMutation: ReturnType<typeof useRefinerJobCancelPendingMutation>;
}) {
  const showCancel = canCancel && job.status === "pending";
  return (
    <tr className="border-b border-[var(--mm-border)] align-top text-[var(--mm-text)]" data-testid="refiner-jobs-row">
      <td className="whitespace-nowrap py-2 pr-2 font-mono">{job.id}</td>
      <td className="py-2 pr-2 whitespace-nowrap">{statusLabel(job.status)}</td>
      <td className="max-w-[16rem] break-words py-2 pr-2 font-mono text-[0.8rem] text-[var(--mm-text2)]">{job.job_kind}</td>
      <td className="py-2 pr-2 whitespace-nowrap text-[var(--mm-text2)]">{job.updated_at}</td>
      <td className="max-w-[16rem] break-words py-2 pr-2 text-[var(--mm-text2)]">
        {job.lease_owner ? (
          <span title={job.lease_expires_at ?? ""}>
            {job.lease_owner}
            {job.lease_expires_at ? ` · ${job.lease_expires_at}` : ""}
          </span>
        ) : (
          "—"
        )}
      </td>
      <td className="max-w-[14rem] py-2 pr-2 break-words font-mono text-[0.75rem] text-[var(--mm-text3)]">
        <span title={job.dedupe_key}>{job.dedupe_key.length > 48 ? `${job.dedupe_key.slice(0, 48)}…` : job.dedupe_key}</span>
      </td>
      <td className="py-2 pr-0 text-right">
        {showCancel ? (
          <button
            type="button"
            className={mmActionButtonClass({
              variant: "tertiary",
              disabled: cancelMutation.isPending,
            })}
            disabled={cancelMutation.isPending}
            data-testid={`refiner-jobs-cancel-${job.id}`}
            onClick={() => cancelMutation.mutate(job.id)}
          >
            Cancel pending
          </button>
        ) : null}
      </td>
    </tr>
  );
}
