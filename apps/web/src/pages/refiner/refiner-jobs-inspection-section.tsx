import { useEffect, useId, useState } from "react";
import { Link } from "react-router-dom";
import { MmJobsPagination } from "../../components/overview/mm-overview-cards";
import {
  isHttpErrorFromApi,
  isLikelyNetworkFailure,
} from "../../lib/api/error-guards";
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

const REFINER_JOBS_INSPECTION_FILTER_OPTIONS: {
  value: RefinerJobsInspectionFilter;
  label: string;
}[] = [
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
  const PAGE_SIZE_OPTIONS = [20, 50, 100] as const;
  const me = useMeQuery();
  const filterLabelId = useId();
  const [filter, setFilter] = useState<RefinerJobsInspectionFilter>("recent");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(PAGE_SIZE_OPTIONS[0]);
  const q = useRefinerJobsInspectionQuery(filter);
  const cancel = useRefinerJobCancelPendingMutation();
  const canCancel = canCancelRefinerJobs(me.data?.role);

  const jobs = q.data?.jobs ?? [];
  const totalPages = Math.max(1, Math.ceil(jobs.length / pageSize));
  const pagedRows = jobs.slice((page - 1) * pageSize, page * pageSize);

  useEffect(() => {
    setPage(1);
  }, [filter, pageSize]);

  useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages);
    }
  }, [page, totalPages]);

  return (
    <section
      className="mm-card mm-dash-card mm-module-surface overflow-hidden p-0"
      aria-labelledby="refiner-jobs-inspection-heading"
      data-testid="refiner-jobs-inspection-section"
    >
      <header className="border-b border-[var(--mm-border)] bg-black/10 px-4 py-3.5 sm:px-5 sm:py-4">
        <h2
          id="refiner-jobs-inspection-heading"
          className="text-lg font-semibold tracking-tight text-[var(--mm-text)]"
        >
          Jobs
        </h2>
        <p className="mt-1 text-sm text-[var(--mm-text2)]">
          Pending, running, and recent Refiner work.
        </p>
      </header>
      <div className="space-y-4 px-4 py-4 sm:px-5 sm:py-5">
        <div className="flex flex-col gap-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-3.5 py-3.5 sm:flex-row sm:items-end sm:justify-between sm:px-5 sm:py-4">
          <label className="block min-w-0 flex-1">
            <span
              id={filterLabelId}
              className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]"
            >
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
        </div>
        {q.isPending || me.isPending ? (
          <p className="text-sm text-[var(--mm-text2)]">Loading jobs…</p>
        ) : null}
        {q.isError ? (
          <p
            className="text-sm text-red-600"
            role="alert"
            data-testid="refiner-jobs-inspection-error"
          >
            {isLikelyNetworkFailure(q.error)
              ? "Could not reach the MediaMop API. Check that the backend is running."
              : isHttpErrorFromApi(q.error)
                ? "The server refused this request. Sign in again, then try this page."
                : q.error instanceof Error
                  ? q.error.message
                  : "Could not load Refiner jobs."}
          </p>
        ) : null}

        {cancel.isError ? (
          <p
            className="text-sm text-red-300"
            role="alert"
            data-testid="refiner-jobs-inspection-cancel-error"
          >
            {cancel.error instanceof Error
              ? cancel.error.message
              : "Cancel failed."}
          </p>
        ) : null}

        {!q.isPending && !q.isError && jobs.length === 0 ? (
          <div
            className="space-y-1 rounded border border-[var(--mm-border)] bg-black/10 px-5 py-10 text-center"
            data-testid="refiner-jobs-inspection-empty"
          >
            <p className="text-sm font-medium text-[var(--mm-text)]">
              No jobs match this view
            </p>
            <p className="text-xs text-[var(--mm-text2)]">
              Nothing matches this filter yet. Try{" "}
              <strong className="text-[var(--mm-text2)]">
                Recent (all statuses)
              </strong>{" "}
              for the latest rows.
            </p>
          </div>
        ) : null}

        {!q.isPending && !q.isError && jobs.length > 0 ? (
          <>
            <div className="w-full min-w-0 overflow-x-auto rounded border border-[var(--mm-border)]">
              <table className="w-full min-w-[34rem] text-left text-sm">
                <thead className="bg-black/20 text-[var(--mm-text2)]">
                  <tr>
                    <th className="sticky left-0 top-0 z-30 bg-black/20 px-3 py-2 font-medium">
                      Id
                    </th>
                    <th className="sticky top-0 z-20 bg-black/20 px-3 py-2 font-medium">
                      Status
                    </th>
                    <th className="sticky top-0 z-20 bg-black/20 px-3 py-2 font-medium">
                      Kind
                    </th>
                    <th className="sticky top-0 z-20 bg-black/20 px-3 py-2 font-medium">
                      Updated
                    </th>
                    <th className="sticky top-0 z-20 bg-black/20 px-3 py-2 font-medium">
                      Lease
                    </th>
                    <th className="sticky top-0 z-20 bg-black/20 px-3 py-2 font-medium">
                      Dedupe
                    </th>
                    <th className="sticky top-0 z-20 bg-black/20 px-3 py-2 font-medium" />
                  </tr>
                </thead>
                <tbody>
                  {pagedRows.map((j) => (
                    <RefinerJobRow
                      key={j.id}
                      job={j}
                      canCancel={canCancel}
                      cancelMutation={cancel}
                    />
                  ))}
                </tbody>
              </table>
            </div>
            <MmJobsPagination
              page={page}
              totalPages={totalPages}
              onPageChange={setPage}
              pageSize={pageSize}
              onPageSizeChange={setPageSize}
              pageSizeOptions={[...PAGE_SIZE_OPTIONS]}
            />
          </>
        ) : null}

        <p className="text-xs text-[var(--mm-text2)]">
          Full detail on Refiner outcomes is in the{" "}
          <Link
            to="/app/activity"
            className="text-[var(--mm-accent)] underline"
          >
            Activity log
          </Link>
          .
        </p>
      </div>
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
    <tr
      className="border-t border-[var(--mm-border)] align-top text-[var(--mm-text)]"
      data-testid="refiner-jobs-row"
    >
      <td className="sticky left-0 z-[1] whitespace-nowrap bg-[var(--mm-card-bg)] px-3 py-2 font-mono text-xs text-[var(--mm-text1)]">
        #{job.id}
      </td>
      <td className="whitespace-nowrap px-3 py-2">{statusLabel(job.status)}</td>
      <td className="max-w-[16rem] break-words px-3 py-2 font-mono text-[0.8rem] text-[var(--mm-text2)]">
        {job.job_kind}
      </td>
      <td className="whitespace-nowrap px-3 py-2 text-xs text-[var(--mm-text2)]">
        {job.updated_at}
      </td>
      <td className="max-w-[16rem] break-words px-3 py-2 text-[var(--mm-text2)]">
        {job.lease_owner ? (
          <span title={job.lease_expires_at ?? ""}>
            {job.lease_owner}
            {job.lease_expires_at ? ` · ${job.lease_expires_at}` : ""}
          </span>
        ) : (
          "—"
        )}
      </td>
      <td className="max-w-[14rem] break-words px-3 py-2 font-mono text-[0.75rem] text-[var(--mm-text3)]">
        <span title={job.dedupe_key}>
          {job.dedupe_key.length > 48
            ? `${job.dedupe_key.slice(0, 48)}…`
            : job.dedupe_key}
        </span>
      </td>
      <td className="px-3 py-2 text-right">
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
