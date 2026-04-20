import { NavLink, Outlet, useParams } from "react-router-dom";
import { fetcherSectionTabClass } from "../fetcher/fetcher-menu-button";
import { usePrunerInstanceQuery } from "../../lib/pruner/queries";

export function PrunerInstanceShell() {
  const { instanceId } = useParams();
  const id = Number(instanceId);
  const q = usePrunerInstanceQuery(id);

  if (!Number.isFinite(id) || id <= 0) {
    return (
      <div className="mm-page">
        <p className="text-sm text-red-600">This server link is not valid.</p>
      </div>
    );
  }

  const base = `/app/pruner/instances/${id}`;

  return (
    <div className="mm-page w-full min-w-0" data-testid="pruner-instance-shell">
      <header className="mm-page__intro !mb-0">
        <p className="mm-page__eyebrow">MediaMop</p>
        {q.isLoading ? <h1 className="mm-page__title">Pruner — loading…</h1> : null}
        {q.data ? (
          <>
            <h1 className="mm-page__title">Pruner — {q.data.display_name}</h1>
            <p className="mm-page__subtitle max-w-3xl">
              Pruner helps clean up Emby, Jellyfin, and Plex libraries. This page is for{" "}
              <strong className="text-[var(--mm-text)]">one</strong>{" "}
              <strong className="text-[var(--mm-text)]">{q.data.provider}</strong> server (
              <span className="font-mono text-[0.9em]">{q.data.base_url}</span>). Use the{" "}
              <strong className="text-[var(--mm-text)]">Movies</strong> and <strong className="text-[var(--mm-text)]">TV</strong>{" "}
              tabs for rules, scans, and deletes — nothing is shared between servers or between providers.
            </p>
          </>
        ) : null}
        {q.isError ? (
          <p className="mt-2 text-sm text-red-600" role="alert">
            {(q.error as Error).message}
          </p>
        ) : null}
      </header>

      <nav
        className="mt-3 flex gap-2.5 overflow-x-auto border-b border-[var(--mm-border)] pb-3.5 sm:mt-4 sm:flex-wrap sm:overflow-visible"
        aria-label="Pruner server sections"
        data-testid="pruner-instance-section-tabs"
      >
        <NavLink to={`${base}/overview`} className={({ isActive }) => fetcherSectionTabClass(isActive)} end>
          Overview
        </NavLink>
        <NavLink to={`${base}/movies`} className={({ isActive }) => fetcherSectionTabClass(isActive)}>
          Movies
        </NavLink>
        <NavLink to={`${base}/tv`} className={({ isActive }) => fetcherSectionTabClass(isActive)}>
          TV
        </NavLink>
        <NavLink to={`${base}/connection`} className={({ isActive }) => fetcherSectionTabClass(isActive)}>
          Connection
        </NavLink>
      </nav>

      <div className="mt-6 w-full min-w-0 sm:mt-7" role="tabpanel">
        <Outlet context={{ instanceId: id, instance: q.data }} />
      </div>
    </div>
  );
}
