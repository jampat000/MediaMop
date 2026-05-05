import type { Dispatch, SetStateAction } from "react";
import {
  prunerApplyLabelForRuleFamily,
  type PrunerApplyEligibility,
  type PrunerPreviewRunSummary,
} from "../../lib/pruner/api";
import { previewRunRowCaption } from "./pruner-ui-utils";

function canApplyFromPreviewSnapshot(
  provider: string | undefined,
  row: { outcome: string; candidate_count: number; rule_family_id: string },
): boolean {
  if (!provider || row.outcome !== "success" || row.candidate_count <= 0)
    return false;
  if (provider === "jellyfin" || provider === "emby") return true;
  return (
    provider === "plex" && row.rule_family_id === "missing_primary_media_reported"
  );
}

type PrunerScopePreviewRunsHistoryProps = {
  isProvider: boolean;
  scope: "tv" | "movies";
  runs: PrunerPreviewRunSummary[] | undefined;
  runsLoading: boolean;
  runsError: Error | null;
  fmt: (value: string | null | undefined) => string;
  busy: boolean;
  canOperate: boolean;
  provider: string | undefined;
  ruleFamilyColumnLabel: (id: string) => string;
  loadJsonFor: (runId: string | null | undefined) => Promise<void>;
  openApplyModal: (runId: string) => void;
};

export function PrunerScopePreviewRunsHistory({
  isProvider,
  scope,
  runs,
  runsLoading,
  runsError,
  fmt,
  busy,
  canOperate,
  provider,
  ruleFamilyColumnLabel,
  loadJsonFor,
  openApplyModal,
}: PrunerScopePreviewRunsHistoryProps) {
  if (isProvider) return null;
  return (
    <div className="space-y-2" data-testid="pruner-preview-runs-history">
      <h3 className="text-sm font-semibold text-[var(--mm-text)]">
        Recent scans ({scope === "tv" ? "TV shows" : "Movies"})
      </h3>
      {runsLoading ? (
        <p className="text-sm text-[var(--mm-text2)]">Loading history...</p>
      ) : runsError ? (
        <p className="text-sm text-red-600" role="alert">
          {runsError.message}
        </p>
      ) : runs?.length ? (
        <div className="overflow-x-auto rounded-md border border-[var(--mm-border)]">
          <table className="w-full min-w-[30rem] border-collapse text-left text-sm text-[var(--mm-text)]">
            <thead className="border-b border-[var(--mm-border)] bg-[var(--mm-surface2)] text-xs uppercase text-[var(--mm-text2)]">
              <tr>
                <th className="px-2 py-2">#</th>
                <th className="px-2 py-2">Cleanup type</th>
                <th className="px-2 py-2">When</th>
                <th className="px-2 py-2">Result</th>
                <th className="px-2 py-2">What it means</th>
                <th className="px-2 py-2">Items</th>
                <th className="px-2 py-2"> </th>
              </tr>
            </thead>
            <tbody>
              {runs.map((row, idx) => (
                <tr
                  key={row.preview_run_id}
                  className="border-b border-[var(--mm-border)] align-top"
                >
                  <td className="px-2 py-2 text-xs text-[var(--mm-text2)]">
                    {idx + 1}
                  </td>
                  <td className="px-2 py-2 text-xs text-[var(--mm-text2)]">
                    {ruleFamilyColumnLabel(row.rule_family_id)}
                  </td>
                  <td className="whitespace-nowrap px-2 py-2 text-xs text-[var(--mm-text2)]">
                    {fmt(row.created_at)}
                  </td>
                  <td className="max-w-[14rem] break-words px-2 py-2 text-xs">
                    <span className="font-medium">{row.outcome}</span>
                    {row.unsupported_detail ? (
                      <div className="mt-1 text-[var(--mm-text2)]">
                        {row.unsupported_detail}
                      </div>
                    ) : null}
                    {row.error_message ? (
                      <div className="mt-1 text-red-600">{row.error_message}</div>
                    ) : null}
                  </td>
                  <td
                    className="px-2 py-2 align-top text-[0.7rem] leading-snug text-[var(--mm-text2)]"
                    data-testid={`pruner-preview-run-caption-${row.preview_run_id}`}
                  >
                    {previewRunRowCaption(row)}
                  </td>
                  <td className="whitespace-nowrap px-2 py-2 text-xs">
                    {row.candidate_count}
                    {row.truncated ? " (list stopped at limit)" : ""}
                  </td>
                  <td className="px-2 py-2 space-y-1">
                    <button
                      type="button"
                      className="rounded border border-[var(--mm-border)] px-2 py-1 text-xs font-medium text-[var(--mm-text)] disabled:opacity-50"
                      disabled={busy}
                      onClick={() => void loadJsonFor(row.preview_run_id)}
                    >
                      Raw
                    </button>
                    {canOperate &&
                    canApplyFromPreviewSnapshot(provider, row) ? (
                      <div>
                        <button
                          type="button"
                          className="mt-1 block w-full rounded border border-red-900/50 bg-red-950/30 px-2 py-1 text-left text-xs font-medium text-red-100 disabled:opacity-50"
                          data-testid={`pruner-apply-open-${row.preview_run_id}`}
                          disabled={busy}
                          onClick={() => openApplyModal(row.preview_run_id)}
                        >
                          {prunerApplyLabelForRuleFamily(row.rule_family_id)}
                        </button>
                      </div>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p
          className="text-sm text-[var(--mm-text2)]"
          data-testid="pruner-preview-runs-empty"
        >
          No scans yet for this library. Run a scan from a rule panel above; when
          it finishes, rows appear here with the result, how many items matched,
          and a short explanation (including rules Plex does not support).
        </p>
      )}
    </div>
  );
}

type PrunerScopeApplyModalProps = {
  runId: string | null;
  operatorLabel: string | null;
  applyEligibilityLoading: boolean;
  applyEligibilityError: Error | null;
  applyEligibilityData: PrunerApplyEligibility | undefined;
  fmt: (value: string | null | undefined) => string;
  applySnapshotConfirmed: boolean;
  setApplySnapshotConfirmed: Dispatch<SetStateAction<boolean>>;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => Promise<void>;
};

export function PrunerScopeApplyModal({
  runId,
  operatorLabel,
  applyEligibilityLoading,
  applyEligibilityError,
  applyEligibilityData,
  fmt,
  applySnapshotConfirmed,
  setApplySnapshotConfirmed,
  busy,
  onCancel,
  onConfirm,
}: PrunerScopeApplyModalProps) {
  if (!runId) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="pruner-apply-modal-title"
      data-testid="pruner-apply-modal"
    >
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-4 shadow-xl">
        <h3
          id="pruner-apply-modal-title"
          className="text-base font-semibold text-[var(--mm-text)]"
        >
          {operatorLabel ?? "Delete from last scan"}
        </h3>
        <p className="mt-2 text-sm text-[var(--mm-text2)]">
          This deletes <strong>only</strong> the titles from the saved list you
          opened - MediaMop does not run a new scan or add titles. Items already
          removed on the server are usually counted as skipped; full counts appear
          in Activity when the job finishes.
        </p>
        {applyEligibilityLoading ? (
          <p className="mt-3 text-sm text-[var(--mm-text2)]">
            Checking whether deletion is allowed...
          </p>
        ) : applyEligibilityError ? (
          <p className="mt-3 text-sm text-red-600" role="alert">
            {applyEligibilityError.message}
          </p>
        ) : applyEligibilityData ? (
          <ul className="mt-3 list-inside list-disc space-y-1 text-sm text-[var(--mm-text)]">
            <li>
              Server: <strong>{applyEligibilityData.display_name}</strong> (
              {applyEligibilityData.provider})
            </li>
            <li>
              Library type:{" "}
              <strong>
                {applyEligibilityData.media_scope === "tv" ? "TV shows" : "Movies"}
              </strong>
            </li>
            <li>
              Scan time:{" "}
              {applyEligibilityData.preview_created_at
                ? fmt(applyEligibilityData.preview_created_at)
                : "\u2014"}
            </li>
            <li>
              Items in this list:{" "}
              <strong>{applyEligibilityData.candidate_count}</strong>
            </li>
          </ul>
        ) : null}
        {applyEligibilityData && !applyEligibilityData.eligible ? (
          <p className="mt-3 text-sm text-amber-700" role="status">
            {applyEligibilityData.reasons.length
              ? applyEligibilityData.reasons.join(" ")
              : "These items cannot be deleted right now."}
          </p>
        ) : null}
        {applyEligibilityData?.eligible ? (
          <label className="mt-4 flex cursor-pointer items-start gap-2 text-sm text-[var(--mm-text)]">
            <input
              type="checkbox"
              className="mt-1"
              checked={applySnapshotConfirmed}
              onChange={(e) => setApplySnapshotConfirmed(e.target.checked)}
            />
            <span>
              I confirm <strong>{operatorLabel}</strong> for this saved list of up
              to {applyEligibilityData.candidate_count} titles.
            </span>
          </label>
        ) : null}
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <button
            type="button"
            className="rounded-md border border-[var(--mm-border)] px-3 py-1.5 text-sm font-medium text-[var(--mm-text)]"
            onClick={() => onCancel()}
          >
            Cancel
          </button>
          <button
            type="button"
            className="rounded-md bg-red-800 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            data-testid="pruner-apply-confirm"
            disabled={
              busy ||
              !applyEligibilityData?.eligible ||
              !applySnapshotConfirmed ||
              applyEligibilityLoading ||
              Boolean(applyEligibilityError)
            }
            onClick={() => void onConfirm()}
          >
            {operatorLabel ?? "Confirm delete"}
          </button>
        </div>
      </div>
    </div>
  );
}
