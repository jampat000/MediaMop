import { Link } from "react-router-dom";
import { usePrunerInstancesQuery } from "../../lib/pruner/queries";

export function PrunerInstancesListPage() {
  const q = usePrunerInstancesQuery();

  return (
    <div className="mm-page w-full min-w-0" data-testid="pruner-scope-page">
      <header className="mm-page__intro !mb-0">
        <p className="mm-page__eyebrow">MediaMop</p>
        <h1 className="mm-page__title">Pruner</h1>
        <p className="mm-page__subtitle max-w-3xl">
          Rule-based <strong className="text-[var(--mm-text)]">library cleanup</strong> for Jellyfin, Emby, and Plex —
          one registered server per row. Open a server to configure <strong className="text-[var(--mm-text)]">TV</strong>{" "}
          and <strong className="text-[var(--mm-text)]">Movies</strong> separately; nothing is shared across instances
          or providers.
        </p>
      </header>

      <section className="mt-6 max-w-3xl" aria-labelledby="pruner-instances-heading">
        <h2 id="pruner-instances-heading" className="text-base font-semibold text-[var(--mm-text1)]">
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
            No instances yet. Operators can register a server from the API; this list updates when instances exist.
          </p>
        ) : null}
        {q.data && q.data.length > 0 ? (
          <ul
            className="mt-3 divide-y divide-[var(--mm-border)] rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)]"
            data-testid="pruner-instances-list"
          >
            {q.data.map((row) => (
              <li key={row.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <div className="font-medium text-[var(--mm-text1)]">{row.display_name}</div>
                  <div className="text-xs text-[var(--mm-text2)]">
                    <span className="font-medium capitalize text-[var(--mm-text)]">{row.provider}</span>
                    <span className="text-[var(--mm-text3)]"> · </span>
                    <span className="break-all font-mono text-[0.85em]">{row.base_url}</span>
                  </div>
                </div>
                <Link
                  to={`/app/pruner/instances/${row.id}/overview`}
                  className="shrink-0 rounded-md border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-3 py-1.5 text-sm font-medium text-[var(--mm-text)] underline-offset-2 hover:bg-[var(--mm-card-bg)] hover:underline"
                >
                  Open workspace
                </Link>
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      <p className="mt-6 max-w-3xl text-xs text-[var(--mm-text2)]">
        Finished previews and apply jobs also appear on{" "}
        <Link className="font-semibold text-[var(--mm-accent)] underline-offset-2 hover:underline" to="/app/activity">
          Activity
        </Link>
        . Provider-specific limits (for example Plex missing-primary caps) stay visible on the scope tabs where they apply.
      </p>
    </div>
  );
}
