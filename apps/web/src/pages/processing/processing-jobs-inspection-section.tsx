import { useEffect, useId, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { MmJobsPagination } from "../../components/overview/mm-overview-cards";
import {
  isHttpErrorFromApi,
  isLikelyNetworkFailure,
} from "../../lib/api/error-guards";
import { useMeQuery } from "../../lib/auth/queries";
import type { ProcessingJobsInspectionFilter } from "../../lib/processing/jobs-inspection/queries";
import {
  useProcessingJobCancelPendingMutation,
  useProcessingJobRecoverFinalizeFailedMutation,
  useProcessingJobsInspectionQuery,
} from "../../lib/processing/jobs-inspection/queries";
import type { ProcessingJobInspectionRow } from "../../lib/processing/jobs-inspection/types";
import { MmListboxPicker } from "../../components/ui/mm-listbox-picker";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import { useAppDateFormatter } from "../../lib/ui/mm-format-date";
import { usePauseQuery } from "../../lib/pause/pause-queries";

function canCancelProcessingJobs(role: string | undefined): boolean {
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
    "processing.watched_folder.remux_scan_dispatch.v1": "Check watched folders",
    "processing.candidate_gate.v1": "Check file readiness",
    "processing.supplied_payload_evaluation.v1":
      "Check a manually supplied file",
    "processing.file.remux_pass.v1": "Process media file",
    "processing.work_temp_stale_sweep.v1": "Clean temporary work files",
    "processing.failure_cleanup.v1": "Clean failed work files",
  };
  if (labels[jobKind]) return labels[jobKind];
  const last = jobKind.split(".").filter(Boolean).at(-2) ?? jobKind;
  return last
    .replaceAll("_", " ")
    .replace(/^./, (value) => value.toUpperCase());
}

function technicalJobSummary(job: ProcessingJobInspectionRow): string {
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

const PROCESSING_JOBS_INSPECTION_FILTER_OPTIONS: {
  value: ProcessingJobsInspectionFilter;
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
): ProcessingJobsInspectionFilter | null {
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

/** Read ``jobs`` lifecycle here; finished outcomes stay on Activity. */
export function ProcessingJobsInspectionSection() {
  const PAGE_SIZE_OPTIONS = [20, 50, 100] as const;
  const me = useMeQuery();
  const pause = usePauseQuery();
  const [searchParams] = useSearchParams();
  const filterLabelId = useId();
  const urlFilter = filterFromUrl(searchParams.get("status"));
  const [filter, setFilter] = useState<ProcessingJobsInspectionFilter>(
    () => urlFilter ?? "recent",
  );
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(PAGE_SIZE_OPTIONS[0]);
  const q = useProcessingJobsInspectionQuery(filter);
  const cancel = useProcessingJobCancelPendingMutation();
  const recover = useProcessingJobRecoverFinalizeFailedMutation();
  const canCancel = canCancelProcessingJobs(me.data?.role);
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
      className="mm-quiet-stack"
      aria-labelledby="processing-jobs-inspection-heading"
      data-testid="processing-jobs-inspection-section"
    >
      <div className="mm-quiet-section">
        <div className="mm-quiet-section__head">
          <h2
            id="processing-jobs-inspection-heading"
            className="mm-quiet-section__title"
          >
            Jobs
          </h2>
        </div>
        <div className="mm-quiet-section__body space-y-4">
          <p className="mm-quiet-note">
            Current and recent work, with a clear next step when you need to
            act.
          </p>
          {/* No lead band here, deliberately: GET /api/v1/processing/jobs/inspection
              answers for one filter at a time and returns no counts for the others, so
              a proportional band would have nothing honest to size itself from. Per
              docs/design/content-language.md rule 1, a page with no real "now" starts
              at rule 3 rather than inventing one. */}
          <label className="block min-w-0 max-w-xl">
            <span
              id={filterLabelId}
              className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]"
            >
              Show jobs
            </span>
            <MmListboxPicker
              className="mt-2"
              data-testid="processing-jobs-inspection-filter"
              ariaLabelledBy={filterLabelId}
              placeholder="Select filter"
              options={PROCESSING_JOBS_INSPECTION_FILTER_OPTIONS}
              value={filter}
              onChange={(v) => setFilter(v as ProcessingJobsInspectionFilter)}
            />
          </label>
          {q.isPending || me.isPending ? (
            <p className="text-sm text-[var(--mm-text2)]">Loading jobs…</p>
          ) : null}
          {q.isError ? (
            <p
              className="text-sm text-[var(--mm-status-failed-text)]"
              role="alert"
              data-testid="processing-jobs-inspection-error"
            >
              {isLikelyNetworkFailure(q.error)
                ? "Could not reach the Weir API. Check that the backend is running."
                : isHttpErrorFromApi(q.error)
                  ? "The server refused this request. Sign in again, then try this page."
                  : q.error instanceof Error
                    ? q.error.message
                    : "Could not load jobs."}
            </p>
          ) : null}

          {cancel.isError ? (
            <p
              className="text-sm text-[var(--mm-status-failed-text)]"
              role="alert"
              data-testid="processing-jobs-inspection-cancel-error"
            >
              {cancel.error instanceof Error
                ? cancel.error.message
                : "Cancel failed."}
            </p>
          ) : null}
          {recover.isError ? (
            <p
              className="text-sm text-[var(--mm-status-failed-text)]"
              role="alert"
              data-testid="processing-jobs-inspection-recover-error"
            >
              {recover.error instanceof Error
                ? recover.error.message
                : "Recovery failed."}
            </p>
          ) : null}

          {!q.isPending && !q.isError && jobs.length === 0 ? (
            <div
              className="py-6"
              data-testid="processing-jobs-inspection-empty"
            >
              <p className="text-sm font-medium text-[var(--mm-text1)]">
                No jobs match this view
              </p>
              <p className="mt-1 text-xs text-[var(--mm-text2)]">
                Nothing matches this filter yet. Try{" "}
                <strong className="text-[var(--mm-text2)]">Recent work</strong>{" "}
                for the latest rows.
              </p>
            </div>
          ) : null}

          {!q.isPending && !q.isError && jobs.length > 0 ? (
            <>
              {/* The horizontal scroll container is load-bearing twice over: it is what
                  lets a 46rem table live in a narrow panel, and it is the scrollport the
                  sticky "Job" column pins itself to. Rule 3 takes this wrapper's border
                  away, not the wrapper. The sticky cells need an opaque backdrop or rows
                  scroll through them, and --mm-bg-main is the surface the de-carded tab
                  now sits on — opaque in both themes, unlike the bg-black/NN wells this
                  used to use (those remap to a 4.5%-alpha well on the light theme).

                  Both the min-width and the sticky stop at 761px, because at 760px and
                  below .mm-quiet-table stops being a table and becomes stacked rows. Left
                  on, the min-width kept forcing a 736px scroll box around content that was
                  already one column wide, and pushed every row off the side of a phone. */}
              <div className="mm-quiet-table-wrap w-full min-w-0">
                <table className="mm-quiet-table min-[761px]:min-w-[46rem]">
                  <thead>
                    <tr>
                      <th
                        scope="col"
                        className="min-[761px]:sticky left-0 top-0 z-30 bg-[var(--mm-bg-main)] pr-4"
                      >
                        Job
                      </th>
                      <th
                        scope="col"
                        className="min-[761px]:sticky top-0 z-20 bg-[var(--mm-bg-main)]"
                      >
                        Status
                      </th>
                      <th
                        scope="col"
                        className="min-[761px]:sticky top-0 z-20 bg-[var(--mm-bg-main)]"
                      >
                        Updated
                      </th>
                      <th
                        scope="col"
                        className="min-[761px]:sticky top-0 z-20 bg-[var(--mm-bg-main)]"
                      >
                        What happened and what to do
                      </th>
                      <th
                        scope="col"
                        className="min-[761px]:sticky top-0 z-20 bg-[var(--mm-bg-main)]"
                      >
                        <span className="sr-only">Action</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {pagedRows.map((j) => (
                      <ProcessingJobRow
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
            Full detail on each outcome is in the{" "}
            <Link to="/activity" className="text-[var(--mm-accent)] underline">
              Activity log
            </Link>
            .
          </p>
        </div>
      </div>
    </section>
  );
}

function ProcessingJobRow({
  job,
  canCancel,
  cancelMutation,
  recoverMutation,
  formatDate,
  processingPaused,
}: {
  job: ProcessingJobInspectionRow;
  canCancel: boolean;
  cancelMutation: ReturnType<typeof useProcessingJobCancelPendingMutation>;
  recoverMutation: ReturnType<
    typeof useProcessingJobRecoverFinalizeFailedMutation
  >;
  formatDate: (iso: string) => string;
  processingPaused: boolean;
}) {
  const showCancel = canCancel && job.status === "pending";
  const showRecover = canCancel && job.status === "handler_ok_finalize_failed";
  const pausedPending = processingPaused && job.status === "pending";
  return (
    <tr data-testid="processing-jobs-row">
      {/* Sticky to the wrapper's scrollport, same as the header cell above it, and on the
          same opaque token so the two read as one pinned column while rows slide under. */}
      <th
        scope="row"
        className="mm-quiet-table__name min-[761px]:sticky left-0 z-[1] max-w-[16rem] bg-[var(--mm-bg-main)] pr-4"
      >
        <span className="block">{jobKindLabel(job.job_kind)}</span>
        <span className="mm-quiet-table__sub font-mono">Job #{job.id}</span>
      </th>
      <td data-label="Status" className="whitespace-nowrap">
        {statusLabel(job.status)}
      </td>
      <td
        data-label="Updated"
        className="whitespace-nowrap text-xs text-[var(--mm-text2)]"
      >
        {formatDate(job.updated_at)}
      </td>
      <td
        data-label="What happened"
        className="min-w-[19rem] max-w-[28rem] break-words"
      >
        <p className="text-sm text-[var(--mm-text1)]">
          {pausedPending
            ? "This job is safely waiting because Weir is paused."
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
          {/* Verbatim diagnostic text, not a content card: the box is what marks it as
              raw output, so rule 3 leaves it alone. Its well is a token rather than a
              bg-black/NN utility so it is deliberate in both themes. */}
          <pre className="mt-1 max-h-36 overflow-auto whitespace-pre-wrap break-words rounded border border-[var(--mm-border)] bg-[var(--mm-well-bg)] p-2">
            {technicalJobSummary(job)}
            {job.technical_detail || job.last_error
              ? `\n\n${job.technical_detail || job.last_error}`
              : ""}
          </pre>
        </details>
      </td>
      <td data-label="Action" className="text-right">
        {showCancel ? (
          <button
            type="button"
            className={mmActionButtonClass({
              variant: "tertiary",
              disabled: cancelMutation.isPending,
            })}
            disabled={cancelMutation.isPending}
            data-testid={`processing-jobs-cancel-${job.id}`}
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
            data-testid={`processing-jobs-recover-${job.id}`}
            onClick={() => recoverMutation.mutate(job.id)}
          >
            {recoverMutation.isPending ? "Recovering…" : "Recover result"}
          </button>
        ) : null}
      </td>
    </tr>
  );
}
