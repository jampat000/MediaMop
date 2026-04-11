import type { FetcherFailedImportAxisSummary } from "../../lib/fetcher/failed-imports/types";
import { useFailedImportAutomationSummaryQuery } from "../../lib/fetcher/failed-imports/queries";

function formatFinishedAt(iso: string | null): string {
  if (!iso) {
    return "—";
  }
  const d = new Date(iso);
  if (Number.isNaN(d.valueOf())) {
    return iso;
  }
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(d);
}

function AxisBlock({ title, axis }: { title: string; axis: FetcherFailedImportAxisSummary }) {
  return (
    <div className="space-y-2 rounded-md border border-[var(--mm-border)] bg-[var(--mm-surface2)]/40 p-3">
      <h3 className="text-sm font-semibold text-[var(--mm-text1)]">{title}</h3>
      <dl className="space-y-1 text-sm text-[var(--mm-text2)]">
        <div className="flex flex-col gap-0.5 sm:flex-row sm:gap-2">
          <dt className="shrink-0 text-[var(--mm-text3)]">Last finished</dt>
          <dd className="font-medium text-[var(--mm-text1)]">{formatFinishedAt(axis.last_finished_at)}</dd>
        </div>
        <div className="flex flex-col gap-0.5 sm:flex-row sm:gap-2">
          <dt className="shrink-0 text-[var(--mm-text3)]">Last outcome</dt>
          <dd>{axis.last_outcome_label}</dd>
        </div>
        <div className="flex flex-col gap-0.5 sm:flex-row sm:gap-2">
          <dt className="shrink-0 text-[var(--mm-text3)]">Saved schedule</dt>
          <dd>
            <span className="text-[var(--mm-text1)]">{axis.saved_schedule_primary}</span>
            {axis.saved_schedule_secondary ? (
              <span className="mt-1 block text-xs text-[var(--mm-text3)]">{axis.saved_schedule_secondary}</span>
            ) : null}
          </dd>
        </div>
      </dl>
    </div>
  );
}

export function FetcherAutomationSummaryStrip() {
  const q = useFailedImportAutomationSummaryQuery();

  if (q.isPending) {
    return (
      <section
        className="mm-card mm-dash-card mm-fetcher-module-surface mt-6"
        aria-busy="true"
        aria-label="Automation summary"
        data-testid="fetcher-automation-summary"
      >
        <p className="mm-card__body text-sm text-[var(--mm-text3)]">Loading automation summary…</p>
      </section>
    );
  }

  if (q.isError) {
    return (
      <section
        className="mm-card mm-dash-card mm-fetcher-module-surface mt-6 border-amber-600/40"
        aria-label="Automation summary"
        data-testid="fetcher-automation-summary"
      >
        <p className="mm-card__body text-sm text-[var(--mm-text2)]">Could not load automation summary.</p>
      </section>
    );
  }

  const d = q.data;

  return (
    <section
      className="mm-card mm-dash-card mm-fetcher-module-surface mt-6"
      aria-labelledby="fetcher-automation-summary-heading"
      data-testid="fetcher-automation-summary"
    >
      <h2 id="fetcher-automation-summary-heading" className="mm-card__title text-lg">
        Automation summary
      </h2>
      <p className="mm-card__body mm-card__body--tight text-sm text-[var(--mm-text3)]">{d.scope_note}</p>
      {d.automation_slots_note ? (
        <p className="mm-card__body mm-card__body--tight text-sm text-[var(--mm-text2)]">{d.automation_slots_note}</p>
      ) : null}
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <AxisBlock title="Movies" axis={d.movies} />
        <AxisBlock title="TV shows" axis={d.tv_shows} />
      </div>
    </section>
  );
}
