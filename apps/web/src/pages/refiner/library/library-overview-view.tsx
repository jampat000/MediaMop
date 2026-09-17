/**
 * Issue #568's Overview: what the library holds and its state at a glance — totals, how many files match the
 * rules / would change / cannot be processed, and the five breakdowns as small bar tables. Every number comes
 * from one aggregate endpoint; nothing is counted in the browser.
 */
import {
  formatBytes,
  LIBRARY_FACETS,
  LIBRARY_FACET_LABELS,
  type LibraryFacet,
  type LibraryOverview,
} from "../../../lib/refiner/library-api";
import { LibraryBreakdownTable } from "./library-breakdown-table";

export type LibraryOverviewViewProps = {
  overview: LibraryOverview;
  onShowFiles: (facet: LibraryFacet, value: string) => void;
  onOpenProblems: () => void;
  /** Shown instead of the numbers when nothing has been scanned yet. */
  emptyState: React.ReactNode;
};

function Figure({
  label,
  value,
  detail,
  testId,
}: {
  label: string;
  value: string;
  detail?: string;
  testId: string;
}) {
  return (
    <div
      className="mm-bubble flex min-w-[9rem] flex-1 flex-col gap-1 p-4"
      data-testid={testId}
    >
      <span className="text-xs font-medium uppercase tracking-wide text-[var(--mm-text3)]">
        {label}
      </span>
      <span className="text-2xl font-semibold tabular-nums text-[var(--mm-text1)]">
        {value}
      </span>
      {detail ? (
        <span className="text-xs text-[var(--mm-text3)]">{detail}</span>
      ) : null}
    </div>
  );
}

export function LibraryOverviewView({
  overview,
  onShowFiles,
  onOpenProblems,
  emptyState,
}: LibraryOverviewViewProps) {
  const { totals } = overview;
  if (totals.files === 0) {
    return <>{emptyState}</>;
  }

  const problemFiles = overview.problems.reduce(
    (sum, group) => sum + group.files,
    0,
  );

  return (
    <div className="flex w-full min-w-0 flex-col gap-4">
      <div
        className="flex flex-wrap gap-3"
        data-testid="library-overview-figures"
      >
        <Figure
          label="Files"
          value={totals.files.toLocaleString()}
          detail={formatBytes(totals.size_bytes)}
          testId="library-figure-files"
        />
        <Figure
          label="Match the rules"
          value={totals.matches.toLocaleString()}
          detail="Nothing to do"
          testId="library-figure-matches"
        />
        <Figure
          label="Would change"
          value={totals.would_change.toLocaleString()}
          detail={`About ${formatBytes(totals.estimated_bytes_saved)} saved`}
          testId="library-figure-would-change"
        />
        <Figure
          label="Cannot be processed"
          value={totals.cannot_process.toLocaleString()}
          detail={
            totals.cannot_process > 0 ? "Weir will not touch these" : undefined
          }
          testId="library-figure-cannot-process"
        />
      </div>

      {problemFiles > 0 ? (
        <button
          type="button"
          className="mm-bubble p-3 text-left text-sm text-[var(--mm-status-warning-text)]"
          onClick={onOpenProblems}
          data-testid="library-overview-problems-link"
        >
          {problemFiles} file(s) Weir will not clean as things stand. See
          Problems for what to do about each.
        </button>
      ) : null}

      {LIBRARY_FACETS.map((facet) => (
        <LibraryBreakdownTable
          key={facet}
          facet={facet}
          heading={LIBRARY_FACET_LABELS[facet]}
          rows={overview.breakdowns[facet] ?? []}
          onShowFiles={onShowFiles}
          emptyMessage="Nothing scanned carries this yet."
        />
      ))}
    </div>
  );
}
