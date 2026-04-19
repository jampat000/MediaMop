import { Link } from "react-router-dom";
import { useSubberJobsQuery } from "../../lib/subber/subber-queries";

export function SubberJobsTab() {
  const q = useSubberJobsQuery(50);
  return (
    <div className="space-y-3" data-testid="subber-jobs-tab">
      {q.isLoading ? <p className="text-sm text-[var(--mm-text2)]">Loading jobs…</p> : null}
      {q.isError ? <p className="text-sm text-red-600">{(q.error as Error).message}</p> : null}
      {q.data?.jobs?.length ? (
        <div className="overflow-x-auto rounded border border-[var(--mm-border)]">
          <table className="w-full min-w-[36rem] text-left text-sm">
            <thead className="bg-black/20 text-[var(--mm-text2)]">
              <tr>
                <th className="px-3 py-2">Id</th>
                <th className="px-3 py-2">Kind</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Scope</th>
                <th className="px-3 py-2">Updated</th>
              </tr>
            </thead>
            <tbody>
              {q.data.jobs.map((j) => (
                <tr key={j.id} className="border-t border-[var(--mm-border)]">
                  <td className="px-3 py-2 font-mono">{j.id}</td>
                  <td className="px-3 py-2 font-mono text-xs">{j.job_kind}</td>
                  <td className="px-3 py-2">{j.status}</td>
                  <td className="px-3 py-2">{j.scope ?? "—"}</td>
                  <td className="px-3 py-2 text-xs">{j.updated_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : q.data ? (
        <div className="space-y-2">
          <p className="text-sm text-[var(--mm-text2)]">No recent Subber jobs.</p>
          <p className="text-xs text-[var(--mm-text2)]">
            If you have triggered a sync or search and nothing appears here, check that MEDIAMOP_SUBBER_WORKER_COUNT is
            set to 1 or more in your backend .env file and restart the backend.
          </p>
        </div>
      ) : null}
      <p className="text-xs text-[var(--mm-text2)]">
        Full detail on every subtitle search, sync result, and any errors is in the{" "}
        <Link to="/app/activity" className="text-[var(--mm-accent)] underline">
          Activity log
        </Link>
        .
      </p>
    </div>
  );
}
