/** Pruner module — durable ``pruner_jobs`` lane (see ADR-0007). Phase 1: infrastructure only. */

export function PrunerPage() {
  return (
    <div className="mm-page" data-testid="pruner-scope-page">
      <header className="mm-page__header">
        <p className="mm-page__eyebrow">Module</p>
        <h1 className="mm-page__title">Pruner</h1>
        <p className="mm-page__lede max-w-3xl text-[var(--mm-text2)]">
          Pruner is           for <strong>rule-based removal of media</strong> from your libraries (deletion workflows). It is not
          for re-encoding or other work outside removal. Integration will target{" "}
          <strong>Emby, Jellyfin, and Plex</strong> as first-class peers, with{" "}
          <strong>per server instance</strong> ownership and <strong>separate TV and Movies</strong> surfaces—see{" "}
          <code className="rounded bg-[var(--mm-surface2)] px-1 py-0.5 text-[0.85em]">
            docs/pruner-forward-design-constraints.md
          </code>{" "}
          in this repository.
        </p>
      </header>

      <section
        className="mt-8 max-w-3xl space-y-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-4"
        aria-labelledby="pruner-status-heading"
      >
        <h2 id="pruner-status-heading" className="text-base font-semibold text-[var(--mm-text)]">
          What ships in Phase 1
        </h2>
        <p className="text-sm text-[var(--mm-text2)]">
          The durable job queue (<code className="text-[0.85em]">pruner_jobs</code>),{" "}
          <code className="text-[0.85em]">pruner.*</code> job kinds, and in-process workers are wired.{" "}
          <strong>No removal jobs or operator APIs are available yet</strong>—the next phases add real Pruner work
          against your media servers.
        </p>
        <p className="text-sm text-[var(--mm-text2)]">
          Background workers are controlled with{" "}
          <code className="rounded bg-[var(--mm-surface2)] px-1 py-0.5 text-[0.85em]">MEDIAMOP_PRUNER_WORKER_COUNT</code>{" "}
          on the server (default <code className="text-[0.85em]">0</code> is normal until job families exist).
        </p>
      </section>
    </div>
  );
}
