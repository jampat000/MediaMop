/**
 * Issue #568's Overview: what the library holds and its state at a glance — totals, how many files match the
 * rules / would change / cannot be processed, and the five breakdowns as small bar tables. Every number comes
 * from one aggregate endpoint; nothing is counted in the browser.
 *
 * Laid out to docs/design/content-language.md rule 2: "Would change" is the one number that carries this tab,
 * so it gets the wide tile and the other three totals qualify it from narrow ones beside it. There is no lead
 * band here — a library census is not a "now", and the tab already says how many files it holds one line
 * above, in the scan sentence.
 */
import {
  formatBytes,
  LIBRARY_FACETS,
  LIBRARY_FACET_LABELS,
  type LibraryFacet,
  type LibraryOverview,
  type LibraryProblemKind,
} from "../../../lib/processing/library-api";
import { plural } from "../../../lib/ui/mm-plural";
import { LibraryBreakdownTable } from "./library-breakdown-table";

export type LibraryOverviewViewProps = {
  overview: LibraryOverview;
  onShowFiles: (facet: LibraryFacet, value: string) => void;
  onOpenProblems: () => void;
  /** Shown instead of the numbers when nothing has been scanned yet. */
  emptyState: React.ReactNode;
};

/** One of the three narrow tiles beside the hero. */
function Support({
  label,
  value,
  note,
  warn,
  testId,
}: {
  label: string;
  value: string;
  note?: string;
  warn?: boolean;
  testId: string;
}) {
  return (
    <section
      className={`mm-figure${warn ? " mm-figure--warn" : ""}`}
      data-testid={testId}
    >
      <div className="mm-figure__eyebrow">
        <span>{label}</span>
      </div>
      <div className="mm-figure__value">{value}</div>
      {note ? <p className="mm-figure__note">{note}</p> : null}
    </section>
  );
}

/**
 * The problem kinds a clean's own preflight finds on a file the scan said it would change. Every other kind is
 * the scan's reason for calling a file "cannot be processed", so those files are already in that tile.
 */
const HELD_BACK_KINDS: ReadonlySet<LibraryProblemKind> = new Set([
  "seeding",
  "manager_redownload",
]);

/**
 * The attention line above the figure row, or null when nothing needs attention. Its first number is the
 * "Cannot be processed" tile's own number, read from the same total, so the two can never disagree. Files that
 * could be processed but that Weir is holding back (still shared with a download, or the manager would fetch
 * them again) are named separately, because they are not in that tile. The server keeps the Problems groups
 * disjoint, and puts every "cannot be processed" file in exactly one of them, so the Problems view adds up to
 * the same total this line gives.
 */
export function problemsSentence(overview: LibraryOverview): string | null {
  const cannot = overview.totals.cannot_process;
  const heldBack = overview.problems
    .filter((group) => HELD_BACK_KINDS.has(group.kind))
    .reduce((sum, group) => sum + group.files, 0);
  if (cannot > 0 && heldBack > 0) {
    return `${plural(cannot, "file", "files")} Weir cannot process, and ${heldBack.toLocaleString()} more it will not clean as things stand.`;
  }
  if (cannot > 0) {
    return `${plural(cannot, "file", "files")} Weir cannot process.`;
  }
  if (heldBack > 0) {
    return `${plural(heldBack, "file", "files")} Weir will not clean as things stand.`;
  }
  return null;
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

  const attention = problemsSentence(overview);

  return (
    <div className="mm-quiet-stack">
      <div className="mm-lead">
        {attention ? (
          <ul className="mm-interrupt">
            <li className="mm-interrupt__item">
              <span
                className="mm-interrupt__text"
                data-testid="library-overview-problems"
              >
                {attention} See Problems for what to do about each.
              </span>
              <button
                type="button"
                className="mm-quiet-link"
                onClick={onOpenProblems}
                data-testid="library-overview-problems-link"
              >
                Open Problems →
              </button>
            </li>
          </ul>
        ) : null}

        <div className="mm-figure-row" data-testid="library-overview-figures">
          <section
            className="mm-figure mm-figure--hero"
            data-testid="library-figure-would-change"
          >
            <div className="mm-figure__eyebrow">
              <span>Would change</span>
              <span>If cleaned now</span>
            </div>
            <div className="mm-figure__value">
              {totals.would_change.toLocaleString()}
              <span className="mm-figure__unit">
                files, about {formatBytes(totals.estimated_bytes_saved)} back
              </span>
            </div>
            <div className="mm-figure__foot">
              <div>
                <span className="mm-figure__foot-value">
                  {totals.total_removed_audio_tracks.toLocaleString()}
                </span>
                <span className="mm-figure__foot-label">Audio tracks</span>
              </div>
              <div>
                <span className="mm-figure__foot-value">
                  {totals.total_removed_subtitle_tracks.toLocaleString()}
                </span>
                <span className="mm-figure__foot-label">Subtitle tracks</span>
              </div>
            </div>
          </section>

          <Support
            label="Files"
            value={totals.files.toLocaleString()}
            note={`${formatBytes(totals.size_bytes)} in this library`}
            testId="library-figure-files"
          />
          <Support
            label="Match the rules"
            value={totals.matches.toLocaleString()}
            note="Nothing to do"
            testId="library-figure-matches"
          />
          <Support
            label="Cannot be processed"
            value={totals.cannot_process.toLocaleString()}
            note={
              totals.cannot_process > 0
                ? "Weir will not touch these"
                : "Nothing is out of reach"
            }
            warn={totals.cannot_process > 0}
            testId="library-figure-cannot-process"
          />
        </div>

        <p className="mm-lead-caption">
          <span>
            Every number here is this library&apos;s last scan, counted by the
            server. Cleaning changes only the &quot;would change&quot; files.
          </span>
        </p>
      </div>

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
