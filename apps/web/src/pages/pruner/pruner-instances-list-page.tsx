import { Link } from "react-router-dom";
import { usePrunerInstancesQuery } from "../../lib/pruner/queries";

export function PrunerInstancesListPage() {
  const q = usePrunerInstancesQuery();

  return (
    <div className="mm-page" data-testid="pruner-scope-page">
      <header className="mm-page__header">
        <p className="mm-page__eyebrow">Module</p>
        <h1 className="mm-page__title">Pruner</h1>
        <p className="mm-page__lede max-w-3xl text-[var(--mm-text2)]">
          Rule-based library cleanup — one server instance per row, with separate TV and Movies scopes.{" "}
          <strong>Jellyfin and Emby:</strong> preview then apply for missing primary art (TV = episodes, Movies = one row
          per movie item). <strong>Plex:</strong> the same rule family is <strong>live-only</strong> (no preview/dry run)
          on this screen; paths differ by design.
        </p>
      </header>

      <section className="mt-6 max-w-3xl" aria-labelledby="pruner-instances-heading">
        <h2 id="pruner-instances-heading" className="text-base font-semibold text-[var(--mm-text)]">
          Server instances
        </h2>
        {q.isLoading ? <p className="mt-2 text-sm text-[var(--mm-text2)]">Loading…</p> : null}
        {q.isError ? (
          <p className="mt-2 text-sm text-red-600" role="alert">
            {(q.error as Error).message}
          </p>
        ) : null}
        {q.data && q.data.length === 0 ? (
          <p className="mt-2 text-sm text-[var(--mm-text2)]">
            No instances yet. Use the API{" "}
            <code className="rounded bg-[var(--mm-surface2)] px-1 py-0.5 text-[0.85em]">POST /api/v1/pruner/instances</code>{" "}
            (operator) to register a server; the UI list will appear here.
          </p>
        ) : null}
        {q.data && q.data.length > 0 ? (
          <ul className="mt-3 divide-y divide-[var(--mm-border)] rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)]">
            {q.data.map((row) => (
              <li key={row.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5">
                <div>
                  <div className="font-medium text-[var(--mm-text)]">{row.display_name}</div>
                  <div className="text-xs text-[var(--mm-text2)]">
                    {row.provider} · {row.base_url}
                  </div>
                </div>
                <Link
                  to={`/app/pruner/instances/${row.id}/overview`}
                  className="text-sm font-medium text-[var(--mm-accent)] hover:underline"
                >
                  Open
                </Link>
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      <p className="mt-6 max-w-3xl text-xs text-[var(--mm-text2)]">
        Durable work uses <code className="text-[0.85em]">pruner_jobs</code> (see{" "}
        <code className="text-[0.85em]">MEDIAMOP_PRUNER_WORKER_COUNT</code>). Connection tests and preview jobs enqueue
        rows; <code className="text-[0.85em]">pruner_preview_runs</code> stores Jellyfin/Emby preview candidate snapshots
        (and Plex &quot;unsupported&quot; outcomes where preview does not apply). Plex live removal does not use that
        table.
      </p>
    </div>
  );
}
