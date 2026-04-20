import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { MmListboxPicker } from "../../components/ui/mm-listbox-picker";
import { useAppDateFormatter } from "../../lib/ui/mm-format-date";
import { useSubberJobsQuery } from "../../lib/subber/subber-queries";

const JOB_FILTER_OPTIONS = [
  { value: "recent", label: "Recent (all statuses, newest first)" },
  { value: "pending", label: "Pending" },
  { value: "running", label: "Running" },
  { value: "failed", label: "Failed" },
  { value: "completed", label: "Completed" },
] as const;

const JOB_KIND_LABELS: Record<string, string> = {
  "subber.subtitle_search.tv.v1": "Subtitle search · TV",
  "subber.subtitle_search.movies.v1": "Subtitle search · Movies",
  "subber.library_sync.tv.v1": "Library sync · TV",
  "subber.library_sync.movies.v1": "Library sync · Movies",
  "subber.library_scan.tv.v1": "Library scan · TV",
  "subber.library_scan.movies.v1": "Library scan · Movies",
  "subber.subtitle_upgrade.tv.v1": "Subtitle upgrade · TV",
  "subber.subtitle_upgrade.movies.v1": "Subtitle upgrade · Movies",
  "subber.webhook_import.tv.v1": "Webhook import · TV",
  "subber.webhook_import.movies.v1": "Webhook import · Movies",
};

function jobLabel(kind: string): string {
  return JOB_KIND_LABELS[kind] ?? kind;
}

export function SubberJobsTab() {
  const q = useSubberJobsQuery(50);
  const [statusFilter, setStatusFilter] = useState("recent");
  const filterLabelId = useId();
  const fmt = useAppDateFormatter();

  const filtered =
    statusFilter === "recent" ? (q.data?.jobs ?? []) : (q.data?.jobs ?? []).filter((j) => j.status === statusFilter);

  return (
    <section
      className="rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] shadow-sm"
      data-testid="subber-jobs-tab"
    >
      <header className="border-b border-[var(--mm-border)] bg-black/10 px-5 py-4">
        <h2 className="text-lg font-semibold tracking-tight text-[var(--mm-text)]">Jobs</h2>
        <p className="mt-1 text-sm text-[var(--mm-text2)]">Pending, running, and recent Subber work on this server.</p>
      </header>
      <div className="space-y-4 px-5 py-5">
        <div className="flex flex-col gap-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-4 sm:flex-row sm:items-end sm:justify-between sm:px-5 sm:py-4">
          <label className="block min-w-0 flex-1">
            <span id={filterLabelId} className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
              Show jobs
            </span>
            <MmListboxPicker
              className="mt-2 max-w-xl"
              ariaLabelledBy={filterLabelId}
              placeholder="Recent (all statuses, newest first)"
              options={JOB_FILTER_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
              value={statusFilter}
              onChange={(v) => setStatusFilter(v)}
            />
          </label>
          <p className="w-full text-left text-[0.7rem] leading-snug text-[var(--mm-text3)] sm:w-auto sm:max-w-[14rem] sm:text-right">
            {filtered.length} row{filtered.length === 1 ? "" : "s"} for this filter.
          </p>
        </div>

        {q.isLoading ? (
          <p className="text-sm text-[var(--mm-text2)]">Loading jobs…</p>
        ) : q.isError ? (
          <p className="text-sm text-red-600">{(q.error as Error).message}</p>
        ) : filtered.length > 0 ? (
          <div className="overflow-x-auto rounded border border-[var(--mm-border)]">
            <table className="w-full min-w-[36rem] text-left text-sm">
              <thead className="bg-black/20 text-[var(--mm-text2)]">
                <tr>
                  <th className="px-3 py-2 font-medium">Job</th>
                  <th className="px-3 py-2 font-medium">Scope</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  <th className="px-3 py-2 font-medium">Updated</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((j) => (
                  <tr key={j.id} className="border-t border-[var(--mm-border)]">
                    <td className="max-w-[14rem] break-words px-3 py-2">{jobLabel(j.job_kind)}</td>
                    <td className="whitespace-nowrap px-3 py-2 capitalize text-[var(--mm-text2)]">{j.scope ?? "—"}</td>
                    <td className="px-3 py-2">
                      <span
                        className={
                          j.status === "completed"
                            ? "text-emerald-500"
                            : j.status === "failed"
                              ? "text-red-400"
                              : j.status === "running"
                                ? "text-amber-400"
                                : "text-[var(--mm-text2)]"
                        }
                      >
                        {j.status}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 text-xs text-[var(--mm-text2)]">{fmt(j.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="space-y-1 rounded border border-[var(--mm-border)] bg-black/10 px-5 py-10 text-center">
            <p className="text-sm font-medium text-[var(--mm-text)]">No jobs match this view</p>
            <p className="text-xs text-[var(--mm-text2)]">
              {statusFilter !== "recent"
                ? `Nothing with status "${statusFilter}" yet. Try Recent (all statuses) for the latest rows.`
                : "No Subber jobs yet. Trigger a sync or search to see activity here."}
            </p>
          </div>
        )}

        <p className="text-xs text-[var(--mm-text2)]">
          Full detail on every subtitle search, sync result, and any errors is in the{" "}
          <Link to="/app/activity" className="text-[var(--mm-accent)] underline">
            Activity log
          </Link>
          .
        </p>
      </div>
    </section>
  );
}
