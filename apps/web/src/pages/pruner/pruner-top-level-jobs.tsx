import { useEffect, useId, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { MmJobsPagination } from "../../components/overview/mm-overview-cards";
import { MmListboxPicker } from "../../components/ui/mm-listbox-picker";
import type { PrunerServerInstance } from "../../lib/pruner/api";
import { usePrunerJobsInspectionQuery } from "../../lib/pruner/queries";
import { PRUNER_JOB_FILTER_OPTIONS } from "./pruner-page-constants";
import { parseServerInstanceId } from "./pruner-page-utils";
import { prunerJobKindOperatorLabel } from "./pruner-ui-utils";
import { useAppDateFormatter } from "../../lib/ui/mm-format-date";

function prunerJobStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    pending: "Queued",
    running: "Running",
    completed: "Finished",
    failed: "Failed",
    cancelled: "Cancelled",
  };
  return labels[status] ?? status;
}

export function TopLevelJobs({
  instances,
}: {
  instances: PrunerServerInstance[];
}) {
  const PAGE_SIZE_OPTIONS = [20, 50, 100] as const;
  const formatDate = useAppDateFormatter();
  const jobsQ = usePrunerJobsInspectionQuery(100);
  const byId = useMemo(
    () => new Map(instances.map((x) => [x.id, x])),
    [instances],
  );
  const [statusFilter, setStatusFilter] = useState("recent");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(PAGE_SIZE_OPTIONS[0]);
  const filterLabelId = useId();
  const jobs =
    statusFilter === "recent"
      ? (jobsQ.data?.jobs ?? [])
      : (jobsQ.data?.jobs ?? []).filter((j) => j.status === statusFilter);
  const totalPages = Math.max(1, Math.ceil(jobs.length / pageSize));
  const pagedRows = jobs.slice((page - 1) * pageSize, page * pageSize);

  useEffect(() => {
    setPage(1);
  }, [statusFilter, pageSize]);

  useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages);
    }
  }, [page, totalPages]);
  return (
    <section
      className="rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] shadow-sm"
      data-testid="pruner-top-jobs-tab"
    >
      <header className="border-b border-[var(--mm-border)] bg-black/10 px-4 py-3.5 sm:px-5 sm:py-4">
        <h2 className="text-lg font-semibold tracking-tight text-[var(--mm-text)]">
          Jobs
        </h2>
        <p className="mt-1 text-sm text-[var(--mm-text2)]">
          Current and recent Pruner work, with a clear next step when you need
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
              ariaLabelledBy={filterLabelId}
              placeholder="Recent work (newest first)"
              options={PRUNER_JOB_FILTER_OPTIONS.map((o) => ({
                value: o.value,
                label: o.label,
              }))}
              value={statusFilter}
              onChange={(v) => setStatusFilter(v)}
            />
          </label>
        </div>
        {jobsQ.isLoading ? (
          <p className="text-sm text-[var(--mm-text2)]">Loading jobs...</p>
        ) : null}
        {jobsQ.isError ? (
          <p className="text-sm text-red-600">
            {(jobsQ.error as Error).message}
          </p>
        ) : null}
        {jobs.length ? (
          <>
            <div className="overflow-x-auto rounded-md border border-[var(--mm-border)]">
              <table className="w-full min-w-[48rem] border-collapse text-left text-sm">
                <thead className="bg-black/20 text-[var(--mm-text2)]">
                  <tr>
                    <th className="sticky left-0 top-0 z-30 bg-black/20 px-3 py-2 font-medium">
                      Job
                    </th>
                    <th className="sticky top-0 z-20 bg-black/20 px-3 py-2 font-medium">
                      Status
                    </th>
                    <th className="sticky top-0 z-20 bg-black/20 px-3 py-2 font-medium">
                      Server
                    </th>
                    <th className="sticky top-0 z-20 bg-black/20 px-3 py-2 font-medium">
                      Updated
                    </th>
                    <th className="sticky top-0 z-20 bg-black/20 px-3 py-2 font-medium">
                      What happened and what to do
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {pagedRows.map((job) => {
                    const sid = parseServerInstanceId(job);
                    const inst = sid ? byId.get(sid) : undefined;
                    return (
                      <tr
                        key={job.id}
                        className="border-t border-[var(--mm-border)]"
                      >
                        <td className="sticky left-0 z-[1] max-w-[16rem] bg-[var(--mm-card-bg)] px-3 py-2 align-top text-[var(--mm-text1)]">
                          <p className="font-medium">
                            {prunerJobKindOperatorLabel(job.job_kind)}
                          </p>
                          <p className="mt-1 font-mono text-[0.72rem] text-[var(--mm-text3)]">
                            Job #{job.id}
                          </p>
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 align-top">
                          <span
                            className={
                              job.status === "completed"
                                ? "text-emerald-500"
                                : job.status === "failed"
                                  ? "text-red-400"
                                  : job.status === "running"
                                    ? "text-amber-400"
                                    : "text-[var(--mm-text2)]"
                            }
                          >
                            {prunerJobStatusLabel(job.status)}
                          </span>
                        </td>
                        <td className="max-w-[14rem] break-words px-3 py-2 align-top text-xs">
                          {inst
                            ? inst.display_name
                            : sid
                              ? `Server #${sid}`
                              : "\u2014"}
                        </td>
                        <td className="whitespace-nowrap px-3 py-2 align-top text-xs text-[var(--mm-text2)]">
                          {formatDate(job.updated_at)}
                        </td>
                        <td className="min-w-[19rem] max-w-[28rem] break-words px-3 py-2 align-top text-[var(--mm-text2)]">
                          <p className="text-sm text-[var(--mm-text1)]">
                            {job.operator_message ||
                              "This Pruner job needs a review."}
                          </p>
                          <p className="mt-1 text-xs text-[var(--mm-text3)]">
                            <span className="font-semibold text-[var(--mm-text2)]">
                              Next step:
                            </span>{" "}
                            {job.next_action ||
                              "Open the related Pruner screen to inspect it."}
                          </p>
                          <details className="mt-2 text-xs text-[var(--mm-text3)]">
                            <summary className="cursor-pointer select-none">
                              Technical details
                            </summary>
                            <pre className="mt-1 max-h-36 overflow-auto whitespace-pre-wrap break-words rounded border border-[var(--mm-border)] bg-black/10 p-2">
                              {`Internal kind: ${job.job_kind}\nDedupe key: ${job.dedupe_key}`}
                              {job.technical_detail || job.last_error
                                ? `\n\n${job.technical_detail || job.last_error}`
                                : ""}
                            </pre>
                          </details>
                        </td>
                      </tr>
                    );
                  })}
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
        ) : jobsQ.data ? (
          <div className="space-y-1 rounded border border-[var(--mm-border)] bg-black/10 px-5 py-10 text-center">
            <p className="text-sm font-medium text-[var(--mm-text)]">
              No jobs match this view
            </p>
            <p className="text-xs text-[var(--mm-text2)]">
              {statusFilter !== "recent"
                ? `Nothing with status "${statusFilter}" yet. Try Recent work for the latest rows.`
                : "No recent Pruner jobs yet. Run cleanup or connection tasks to see activity here."}
            </p>
          </div>
        ) : null}
        <p className="text-xs text-[var(--mm-text2)]">
          Full detail on what was deleted, skipped, or failed is in the{" "}
          <Link
            to="/activity"
            className="font-semibold text-[var(--mm-accent)] underline-offset-2 hover:underline"
          >
            Activity log
          </Link>
          .
        </p>
      </div>
    </section>
  );
}
