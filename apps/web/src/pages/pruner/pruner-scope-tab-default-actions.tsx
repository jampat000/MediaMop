import type { Dispatch, SetStateAction } from "react";
import type { PrunerServerInstance } from "../../lib/pruner/api";
import { formatPrunerDateTime } from "./pruner-ui-utils";
import {
  PrunerScopeApplyModal,
  PrunerScopePreviewRunsHistory,
} from "./pruner-scope-tab-history-modal";
import { PrunerScopeScheduleCard } from "./pruner-scope-tab-schedule-card";

type ScopeRow = PrunerServerInstance["scopes"][number] | undefined;

type PrunerScopeTabDefaultActionsProps = {
  instanceId: number;
  scope: "tv" | "movies";
  libraryTabPhrase: string;
  busy: boolean;
  showInteractiveControls: boolean;
  scopeRow: ScopeRow;
  runPreview: () => Promise<void>;
  loadJsonFor: (runUuid?: string | null) => Promise<void>;
  schedEnabled: boolean;
  setSchedEnabled: (value: boolean) => void;
  schedIntervalSec: number;
  schedIntervalMinDraft: string | null;
  setSchedIntervalMinDraft: (value: string | null) => void;
  schedHoursLimited: boolean;
  setSchedHoursLimited: (value: boolean) => void;
  schedDays: string;
  setSchedDays: (value: string) => void;
  schedStart: string;
  setSchedStart: (value: string) => void;
  schedEnd: string;
  setSchedEnd: (value: string) => void;
  fmt: ReturnType<typeof import("../../lib/ui/mm-format-date").useAppDateFormatter>;
  schedMsg: string | null;
  saveSchedule: () => Promise<void>;
  runs: unknown;
  runsLoading: boolean;
  runsError: Error | null;
  canOperate: boolean;
  provider: PrunerServerInstance["provider"] | undefined;
  ruleFamilyColumnLabel: (id: string) => string;
  openApplyModal: (runUuid: string) => void;
  applyModalRunId: string | null;
  applySnapshotOperatorLabel: string | null;
  applyEligibilityLoading: boolean;
  applyEligibilityError: Error | null;
  applyEligibilityData: unknown;
  applySnapshotConfirmed: boolean;
  setApplySnapshotConfirmed: Dispatch<SetStateAction<boolean>>;
  closeApplyModal: () => void;
  confirmApplyFromSnapshot: () => Promise<void>;
  err: string | null;
  preview: string | null;
  jsonPreview: string | null;
};

export function PrunerScopeTabDefaultActions({
  instanceId,
  scope,
  libraryTabPhrase,
  busy,
  showInteractiveControls,
  scopeRow,
  runPreview,
  loadJsonFor,
  schedEnabled,
  setSchedEnabled,
  schedIntervalSec,
  schedIntervalMinDraft,
  setSchedIntervalMinDraft,
  schedHoursLimited,
  setSchedHoursLimited,
  schedDays,
  setSchedDays,
  schedStart,
  setSchedStart,
  schedEnd,
  setSchedEnd,
  fmt,
  schedMsg,
  saveSchedule,
  runs,
  runsLoading,
  runsError,
  canOperate,
  provider,
  ruleFamilyColumnLabel,
  openApplyModal,
  applyModalRunId,
  applySnapshotOperatorLabel,
  applyEligibilityLoading,
  applyEligibilityError,
  applyEligibilityData,
  applySnapshotConfirmed,
  setApplySnapshotConfirmed,
  closeApplyModal,
  confirmApplyFromSnapshot,
  err,
  preview,
  jsonPreview,
}: PrunerScopeTabDefaultActionsProps) {
  return (
    <>
      {scopeRow ? (
        <div
          className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text2)]"
          data-testid="pruner-scope-latest-preview-summary"
        >
          <h3 className="text-sm font-semibold text-[var(--mm-text)]">
            Latest automatic scan (this {libraryTabPhrase})
          </h3>
          <p className="mt-1 text-xs text-[var(--mm-text2)]">
            Quick readout from the last finished scan — use the history table for
            older runs.
          </p>
          <dl className="mt-2 space-y-1 text-xs sm:text-sm">
            <div>
              <dt className="inline text-[var(--mm-text3)]">When</dt>{" "}
              <dd className="inline font-medium text-[var(--mm-text1)]">
                {formatPrunerDateTime(scopeRow.last_preview_at)}
              </dd>
            </div>
            <div>
              <dt className="inline text-[var(--mm-text3)]">Outcome</dt>{" "}
              <dd className="inline font-medium text-[var(--mm-text1)]">
                {scopeRow.last_preview_outcome ?? "—"}
              </dd>
            </div>
            <div>
              <dt className="inline text-[var(--mm-text3)]">Items matched</dt>{" "}
              <dd className="inline font-medium text-[var(--mm-text1)]">
                {scopeRow.last_preview_candidate_count ?? "—"}
              </dd>
            </div>
            <div>
              <dt className="inline text-[var(--mm-text3)]">Problem detail</dt>{" "}
              <dd className="inline text-[var(--mm-text1)]">
                {scopeRow.last_preview_error ?? "—"}
              </dd>
            </div>
          </dl>
        </div>
      ) : null}
      <div>
        <h3
          className="text-base font-semibold text-[var(--mm-text)]"
          data-testid="pruner-actions-history-heading"
        >
          Scan and delete actions
        </h3>
        <p className="text-xs text-[var(--mm-text2)]">
          Run scans, review the table, then delete from one chosen list if you
          want. The table explains empty results and types your server does not
          support.
        </p>
      </div>
      {showInteractiveControls ? (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-md bg-[var(--mm-accent)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            disabled={busy}
            onClick={() => void runPreview()}
          >
            Scan for broken posters
          </button>
          <button
            type="button"
            className="rounded-md border border-[var(--mm-border)] px-3 py-1.5 text-sm font-medium text-[var(--mm-text)] disabled:opacity-50"
            disabled={busy || !scopeRow?.last_preview_run_uuid}
            onClick={() => void loadJsonFor(scopeRow?.last_preview_run_uuid)}
          >
            View last scan results
          </button>
        </div>
      ) : (
        <p className="text-sm text-[var(--mm-text2)]">
          Sign in as an operator to run scans.
        </p>
      )}
      <PrunerScopeScheduleCard
        instanceId={instanceId}
        scope={scope}
        showInteractiveControls={showInteractiveControls}
        busy={busy}
        scopeRow={scopeRow}
        schedEnabled={schedEnabled}
        setSchedEnabled={setSchedEnabled}
        schedIntervalSec={schedIntervalSec}
        schedIntervalMinDraft={schedIntervalMinDraft}
        setSchedIntervalMinDraft={setSchedIntervalMinDraft}
        schedHoursLimited={schedHoursLimited}
        setSchedHoursLimited={setSchedHoursLimited}
        schedDays={schedDays}
        setSchedDays={setSchedDays}
        schedStart={schedStart}
        setSchedStart={setSchedStart}
        schedEnd={schedEnd}
        setSchedEnd={setSchedEnd}
        fmt={fmt}
        schedMsg={schedMsg}
        saveSchedule={saveSchedule}
      />
      <PrunerScopePreviewRunsHistory
        isProvider={false}
        scope={scope}
        runs={runs as never}
        runsLoading={runsLoading}
        runsError={runsError}
        fmt={fmt}
        busy={busy}
        canOperate={canOperate}
        provider={provider}
        ruleFamilyColumnLabel={ruleFamilyColumnLabel}
        loadJsonFor={loadJsonFor}
        openApplyModal={openApplyModal}
      />
      <PrunerScopeApplyModal
        runId={applyModalRunId}
        operatorLabel={applySnapshotOperatorLabel}
        applyEligibilityLoading={applyEligibilityLoading}
        applyEligibilityError={applyEligibilityError}
        applyEligibilityData={applyEligibilityData as never}
        fmt={fmt}
        applySnapshotConfirmed={applySnapshotConfirmed}
        setApplySnapshotConfirmed={setApplySnapshotConfirmed}
        busy={busy}
        onCancel={closeApplyModal}
        onConfirm={confirmApplyFromSnapshot}
      />
      {err ? (
        <p className="text-sm text-red-600" role="alert">
          {err}
        </p>
      ) : null}
      {preview ? <p className="text-sm text-[var(--mm-text)]">{preview}</p> : null}
      {jsonPreview ? (
        <pre className="max-h-96 overflow-auto rounded-md border border-[var(--mm-border)] bg-[var(--mm-surface2)] p-3 text-xs">
          {jsonPreview}
        </pre>
      ) : null}
    </>
  );
}
