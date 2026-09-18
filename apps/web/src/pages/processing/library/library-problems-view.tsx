/**
 * Issue #568's Problems sub-view: every reason Weir will not clean a file, grouped, with a few example paths
 * and one plain sentence about what to do. The grouping and the advice both come from the server, so the
 * wording an operator reads is the same wording the API and its tests use.
 */
import {
  formatBytes,
  type LibraryProblemGroup,
  type LibraryProblemKind,
} from "../../../lib/processing/library-api";
import { mmActionButtonClass } from "../../../lib/ui/mm-control-roles";

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
    <div className="flex w-full min-w-0 flex-col gap-3">
      {groups.map((group) => (
        <section
          key={group.kind}
          className="mm-bubble space-y-2 p-4"
          data-testid="library-problem-group"
        >
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-sm font-semibold text-[var(--mm-text1)]">
              {group.title}
            </h3>
            <span className="text-xs text-[var(--mm-text3)]">
              {group.files} file(s) · {formatBytes(group.size_bytes)}
            </span>
          </div>
          <p className="max-w-prose text-sm text-[var(--mm-text2)]">
            {group.what_to_do}
          </p>
          <ul className="space-y-0.5">
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
          <button
            type="button"
            className={mmActionButtonClass({ variant: "tertiary" })}
            onClick={() => onShowFiles(group.kind)}
          >
            Show files
          </button>
        </section>
      ))}
    </div>
  );
}
