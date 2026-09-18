/**
 * Issue #568's Problems sub-view: every reason Weir will not clean a file, grouped, with a few example paths
 * and one plain sentence about what to do. The grouping and the advice both come from the server, so the
 * wording an operator reads is the same wording the API and its tests use.
 *
 * Rule 3 of docs/design/content-language.md: each group is a heading with its count and its link on the
 * right, a hairline, then the advice and the paths. No boxes.
 */
import {
  formatBytes,
  type LibraryProblemGroup,
  type LibraryProblemKind,
} from "../../../lib/processing/library-api";

export type LibraryProblemsViewProps = {
  groups: LibraryProblemGroup[];
  /** Opens the Files sub-view filtered to one group. */
  onShowFiles: (kind: LibraryProblemKind) => void;
  /** Shown when nothing is wrong, or nothing has been scanned yet. */
  emptyState: React.ReactNode;
};

export function LibraryProblemsView({
  groups,
  onShowFiles,
  emptyState,
}: LibraryProblemsViewProps) {
  if (groups.length === 0) {
    return <>{emptyState}</>;
  }

  return (
    <div className="mm-quiet-stack">
      {groups.map((group) => {
        const headingId = `library-problem-${group.kind}-heading`;
        return (
          <section
            key={group.kind}
            className="mm-quiet-section"
            aria-labelledby={headingId}
            data-testid="library-problem-group"
          >
            <div className="mm-quiet-section__head">
              <h3 id={headingId} className="mm-quiet-section__title">
                {group.title}
              </h3>
              <div className="mm-quiet-section__aside">
                <span className="text-xs text-[var(--mm-text3)]">
                  {group.files} file(s) · {formatBytes(group.size_bytes)}
                </span>
                <button
                  type="button"
                  className="mm-quiet-link"
                  onClick={() => onShowFiles(group.kind)}
                >
                  Show files →
                </button>
              </div>
            </div>
            <div className="mm-quiet-section__body">
              <p className="mm-quiet-note">{group.what_to_do}</p>
              <ul className="mt-3 space-y-0.5">
                {group.sample_paths.map((path) => (
                  <li
                    key={path}
                    className="break-all text-xs text-[var(--mm-text3)]"
                  >
                    {path}
                  </li>
                ))}
                {group.files > group.sample_paths.length ? (
                  <li className="text-xs text-[var(--mm-text3)]">
                    …and {group.files - group.sample_paths.length} more.
                  </li>
                ) : null}
              </ul>
            </div>
          </section>
        );
      })}
    </div>
  );
}
