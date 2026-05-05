import { Link } from "react-router-dom";
import type {
  CandidateDisplayRow,
  PreviewSnapshot,
} from "./pruner-operator-scan-utils";

type PrunerDryRunResultsProps = {
  phase: "idle" | "scanning" | "results" | "deleting";
  err: string | null;
  emptyBecauseNoRules: boolean;
  dryRunEnabled: boolean;
  snapshots: PreviewSnapshot[];
  totalCount: number;
  allRows: CandidateDisplayRow[];
  deleteEligible: Record<string, boolean>;
  deleteReasons: Record<string, string[]>;
  applySummary: string | null;
};

export function PrunerDryRunResults({
  phase,
  err,
  emptyBecauseNoRules,
  dryRunEnabled,
  snapshots,
  totalCount,
  allRows,
  deleteEligible,
  deleteReasons,
  applySummary,
}: PrunerDryRunResultsProps) {
  if (!(phase === "results" || phase === "deleting")) return null;
  return (
    <div className="mt-4 space-y-3">
      {phase === "deleting" ? (
        <p className="text-sm font-medium text-[var(--mm-text1)]">Deleting...</p>
      ) : null}
      {snapshots.length === 0 && phase === "results" && !err && emptyBecauseNoRules ? (
        <p className="text-sm text-[var(--mm-text2)]">
          No cleanup rules are turned on for this column, so there is nothing to
          scan.
        </p>
      ) : null}
      {!dryRunEnabled &&
      phase === "results" &&
      snapshots.length > 0 &&
      totalCount === 0 ? (
        <p className="text-sm text-[var(--mm-text2)]">No items matched your criteria.</p>
      ) : null}
      {(dryRunEnabled || !applySummary) &&
        snapshots.map((s) => (
          <div
            key={s.previewRunId}
            className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-surface2)]/30 p-3"
          >
            <p className="text-sm font-medium text-[var(--mm-text1)]">
              {s.ruleLabel}
              {s.outcome === "unsupported" ? (
                <span className="ml-2 text-xs font-normal text-[var(--mm-text3)]">
                  {" "}
                  - not available for this scan
                </span>
              ) : null}
            </p>
            {s.outcome === "unsupported" && s.unsupportedDetail ? (
              <p className="mt-1 text-xs text-[var(--mm-text3)]">
                {s.unsupportedDetail}
              </p>
            ) : null}
            {s.outcome === "failed" && s.errorMessage ? (
              <p className="mt-1 text-xs text-red-400">{s.errorMessage}</p>
            ) : null}
            {s.outcome === "success" ? (
              <p className="mt-1 text-xs text-[var(--mm-text2)]">
                {s.rows.length} item{s.rows.length === 1 ? "" : "s"} matched
                {s.truncated
                  ? " (list stopped at your scan limit - more may exist on the server)"
                  : ""}
              </p>
            ) : null}
          </div>
        ))}
      {dryRunEnabled && phase === "results" && snapshots.length > 0 ? (
        totalCount > 0 ? (
          <>
            <p className="text-sm text-[var(--mm-text1)]">
              <span className="font-semibold">{totalCount}</span> item
              {totalCount === 1 ? "" : "s"} matched your criteria.
            </p>
            <ul className="max-h-64 divide-y divide-[var(--mm-border)] overflow-y-auto rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] text-sm">
              {allRows.map((r) => (
                <li
                  key={r.key}
                  className="flex flex-col gap-0.5 px-3 py-2 sm:flex-row sm:items-center sm:justify-between"
                >
                  <span className="text-[var(--mm-text1)]">{r.title}</span>
                  <span className="text-xs text-[var(--mm-text3)]">
                    {r.ruleLabel}
                  </span>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="text-sm text-[var(--mm-text2)]">No items matched your criteria.</p>
        )
      ) : null}
      {!dryRunEnabled &&
      snapshots.some(
        (s) =>
          s.outcome === "success" &&
          s.rows.length > 0 &&
          deleteEligible[s.previewRunId] === false,
      ) ? (
        <div className="text-xs text-[var(--mm-text3)]">
          {snapshots.map((s) => {
            if (
              s.outcome !== "success" ||
              s.rows.length === 0 ||
              deleteEligible[s.previewRunId] !== false
            )
              return null;
            const rs = deleteReasons[s.previewRunId] ?? [];
            return (
              <p key={s.previewRunId} className="mt-1">
                <span className="font-medium text-[var(--mm-text2)]">
                  {s.ruleLabel}:
                </span>{" "}
                {rs.join(" ")}
              </p>
            );
          })}
        </div>
      ) : null}
      {applySummary ? (
        <p className="text-sm text-[var(--mm-text1)]">
          {applySummary.includes("taking longer") ? (
            applySummary
          ) : (
            <>
              {applySummary}{" "}
              <Link
                to="/activity"
                className="font-semibold text-[var(--mm-accent)] underline-offset-2 hover:underline"
              >
                Activity log
              </Link>{" "}
              has full detail.
            </>
          )}
        </p>
      ) : null}
      {dryRunEnabled && phase === "results" && totalCount > 0 ? (
        <p className="text-xs text-[var(--mm-text3)]">
          Full detail:{" "}
          <Link
            to="/activity"
            className="font-medium text-[var(--mm-accent)] underline-offset-2 hover:underline"
          >
            Activity log
          </Link>
        </p>
      ) : null}
    </div>
  );
}
