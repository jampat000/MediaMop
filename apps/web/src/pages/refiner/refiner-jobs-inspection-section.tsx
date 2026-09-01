import { useEffect, useId, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { MmJobsPagination } from "../../components/overview/mm-overview-cards";
import {
  isHttpErrorFromApi,
  isLikelyNetworkFailure,
} from "../../lib/api/error-guards";
import { useMeQuery } from "../../lib/auth/queries";
import type { RefinerJobsInspectionFilter } from "../../lib/refiner/jobs-inspection/queries";
import {
  useRefinerJobCancelPendingMutation,
  useRefinerJobRecoverFinalizeFailedMutation,
  useRefinerJobsInspectionQuery,
} from "../../lib/refiner/jobs-inspection/queries";
import type { RefinerJobInspectionRow } from "../../lib/refiner/jobs-inspection/types";
import { MmListboxPicker } from "../../components/ui/mm-listbox-picker";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import { useAppDateFormatter } from "../../lib/ui/mm-format-date";
import { useSuitePauseQuery } from "../../lib/suite/pause-queries";

function canCancelRefinerJobs(role: string | undefined): boolean {
  return role === "operator" || role === "admin";
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    pending: "Queued",
    leased: "Running",
    completed: "Finished",
    failed: "Failed",
    cancelled: "Cancelled",
    handler_ok_finalize_failed: "Recovery needed",
  };
  return labels[status] ?? status;
}

function jobKindLabel(jobKind: string): string {
  const labels: Record<string, string> = {
    "refiner.watched_folder.remux_scan_dispatch.v1": "Check watched folders",
    "refiner.candidate_gate.v1": "Check file readiness",
    "refiner.supplied_payload_evaluation.v1": "Check a manually supplied file",
    "refiner.file.remux_pass.v1": "Process media file",
    "refiner.work_temp_stale_sweep.v1": "Clean temporary work files",
    "refiner.failure_cleanup.v1": "Clean failed work files",
  };
  if (labels[jobKind]) return labels[jobKind];
  const last = jobKind.split(".").filter(Boolean).at(-2) ?? jobKind;
  return last
    .replaceAll("_", " ")
    .replace(/^./, (value) => value.toUpperCase());
}

function technicalJobSummary(job: RefinerJobInspectionRow): string {
  const lines = [
    `Internal kind: ${job.job_kind}`,
    `Dedupe key: ${job.dedupe_key}`,
  ];
  if (job.lease_owner) {
    lines.push(`Worker lease: ${job.lease_owner}`);
  }
  if (job.lease_expires_at) {
    lines.push(`Lease expiry: ${job.lease_expires_at}`);
  }
  return lines.join("\n");
}

const REFINER_JOBS_INSPECTION_FILTER_OPTIONS: {
  value: RefinerJobsInspectionFilter;
  label: string;
}[] = [
  { value: "recent", label: "Recent work (routine successful scans hidden)" },
  { value: "pending", label: "Pending only" },
  { value: "leased", label: "Leased only" },
  { value: "terminal", label: "Terminal (completed, failed, finalize-failed)" },
  { value: "cancelled", label: "Cancelled only" },
  { value: "completed", label: "Completed only" },
  { value: "failed", label: "Failed only" },
  { value: "handler_ok_finalize_failed", label: "Finalize-failed only" },
];

function filterFromUrl(
  value: string | null,
): RefinerJobsInspectionFilter | null {
  if (
    value === "failed" ||
    value === "handler_ok_finalize_failed" ||
    value === "pending" ||
    value === "leased" ||
    value === "completed" ||
    value === "cancelled" ||
    value === "terminal"
  ) {
    return value;
  }
  return null;
}

/** Read ``refiner_jobs`` lifecycle here; finished outcomes stay on Activity. */
export function RefinerJobsInspectionSection() {
  const PAGE_SIZE_OPTIONS = [20, 50, 100] as const;
  const me = useMeQuery();
  const pause = useSuitePauseQuery();
  const [searchParams] = useSearchParams();
  const filterLabelId = useId();
  const urlFilter = filterFromUrl(searchParams.get("status"));
  const [filter, setFilter] = useState<RefinerJobsInspectionFilter>(
    () => urlFilter ?? "recent",
  );
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(PAGE_SIZE_OPTIONS[0]);
  const q = useRefinerJobsInspectionQuery(filter);
  const cancel = useRefinerJobCancelPendingMutation();
  const recover = useRefinerJobRecoverFinalizeFailedMutation();
  const canCancel = canCancelRefinerJobs(me.data?.role);
  const formatDate = useAppDateFormatter();

  const jobs = q.data?.jobs ?? [];
  const totalPages = Math.max(1, Math.ceil(jobs.length / pageSize));
  const pagedRows = jobs.slice((page - 1) * pageSize, page * pageSize);

  useEffect(() => {
    if (urlFilter) setFilter(urlFilter);
  }, [urlFilter]);

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
          Current and recent Refiner work, with a clear next step when you need
          to act.
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
        {recover.isError ? (
          <p
            className="text-sm text-red-300"
            role="alert"
            data-testid="refiner-jobs-inspection-recover-error"
          >
            {recover.error instanceof Error
              ? recover.error.message
              : "Recovery failed."}
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
              <strong className="text-[var(--mm-text2)]">Recent work</strong>{" "}
              for the latest rows.
            </p>
          </div>
        ) : null}

        {!q.isPending && !q.isError && jobs.length > 0 ? (
          <>
            <div className="w-full min-w-0 overflow-x-auto rounded border border-[var(--mm-border)]">
              <table className="w-full min-w-[46rem] text-left text-sm">
                <thead className="bg-black/20 text-[var(--mm-text2)]">
                  <tr>
                    <th className="sticky left-0 top-0 z-30 bg-black/20 px-3 py-2 font-medium">
                      Job
                    </th>
                    <th className="sticky top-0 z-20 bg-black/20 px-3 py-2 font-medium">
                      Status
                    </th>
                    <th className="sticky top-0 z-20 bg-black/20 px-3 py-2 font-medium">
                      Updated
                    </th>
                    <th className="sticky top-0 z-20 bg-black/20 px-3 py-2 font-medium">
                      What happened and what to do
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
                      recoverMutation={recover}
                      formatDate={formatDate}
                      processingPaused={pause.data?.paused === true}
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
          <Link to="/activity" className="text-[var(--mm-accent)] underline">
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
  recoverMutation,
  formatDate,
  processingPaused,
}: {
  job: RefinerJobInspectionRow;
  canCancel: boolean;
  cancelMutation: ReturnType<typeof useRefinerJobCancelPendingMutation>;
  recoverMutation: ReturnType<
    typeof useRefinerJobRecoverFinalizeFailedMutation
  >;
  formatDate: (iso: string) => string;
  processingPaused: boolean;
}) {
  const showCancel = canCancel && job.status === "pending";
  const showRecover = canCancel && job.status === "handler_ok_finalize_failed";
  const pausedPending = processingPaused && job.status === "pending";
  return (
    <tr
      className="border-t border-[var(--mm-border)] align-top text-[var(--mm-text)]"
      data-testid="refiner-jobs-row"
    >
      <td className="sticky left-0 z-[1] max-w-[16rem] bg-[var(--mm-card-bg)] px-3 py-2 text-[var(--mm-text1)]">
        <p className="font-medium">{jobKindLabel(job.job_kind)}</p>
        <p className="mt-1 font-mono text-[0.72rem] text-[var(--mm-text3)]">
          Job #{job.id}
        </p>
      </td>
      <td className="whitespace-nowrap px-3 py-2">{statusLabel(job.status)}</td>
      <td className="whitespace-nowrap px-3 py-2 text-xs text-[var(--mm-text2)]">
        {formatDate(job.updated_at)}
      </td>
      <td className="min-w-[19rem] max-w-[28rem] break-words px-3 py-2 text-[var(--mm-text2)]">
        <p className="text-sm text-[var(--mm-text1)]">
          {pausedPending
            ? "This job is safely waiting because MediaMop is paused."
            : job.operator_message || "This job needs a review."}
        </p>
        <p className="mt-1 text-xs text-[var(--mm-text3)]">
          <span className="font-semibold text-[var(--mm-text2)]">
            Next step:
          </span>{" "}
          {pausedPending
            ? "No action is required. Use Resume at the top of the page when you want queued work to continue."
            : job.next_action || "Open the related screen to inspect the job."}
        </p>
        <details className="mt-2 text-xs text-[var(--mm-text3)]">
          <summary className="cursor-pointer select-none">
            Technical details
          </summary>
          <pre className="mt-1 max-h-36 overflow-auto whitespace-pre-wrap break-words rounded border border-[var(--mm-border)] bg-black/10 p-2">
            {technicalJobSummary(job)}
            {job.technical_detail || job.last_error
              ? `\n\n${job.technical_detail || job.last_error}`
              : ""}
          </pre>
        </details>
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
        {showRecover ? (
          <button
            type="button"
            className={mmActionButtonClass({
              variant: "secondary",
              disabled: recoverMutation.isPending,
            })}
            disabled={recoverMutation.isPending}
            data-testid={`refiner-jobs-recover-${job.id}`}
            onClick={() => recoverMutation.mutate(job.id)}
          >
            {recoverMutation.isPending ? "Recovering…" : "Recover result"}
          </button>
        ) : null}
      </td>
    </tr>
  );
}
