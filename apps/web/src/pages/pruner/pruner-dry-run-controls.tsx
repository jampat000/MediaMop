import {
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";
import {
  fetchPrunerApplyEligibility,
  fetchPrunerInstance,
  fetchPrunerPreviewRun,
  postPrunerApplyFromPreview,
  postPrunerPreview,
} from "../../lib/pruner/api";
import type { PrunerServerInstance } from "../../lib/pruner/api";
import {
  PRUNER_SCAN_POLL_MS,
  PRUNER_SCAN_TIMEOUT_MS,
  displayRowsForCandidates,
  moviesRuleFamiliesToScan,
  parseCandidatesJsonArray,
  resolvePreviewRunIdForJob,
  ruleFamilyOperatorLabel,
  tvRuleFamiliesToScan,
  waitForApplyActivity,
  waitForPrunerJobTerminal,
  type CandidateDisplayRow,
  type PreviewSnapshot,
} from "./pruner-operator-scan-utils";
import { PrunerDryRunResults } from "./pruner-dry-run-results";

function scopeRow(
  inst: PrunerServerInstance | undefined,
  media_scope: "tv" | "movies",
) {
  return inst?.scopes.find((s) => s.media_scope === media_scope);
}

export type PrunerDryRunControlsProps = {
  instanceId: number;
  mediaScope: "tv" | "movies";
  testIdPrefix: string;
  ensureSaved: () => Promise<void>;
  dryRunEnabled: boolean;
  onDryRunEnabledChange: (enabled: boolean) => void;
  runDisabled: boolean;
  controlsDisabled: boolean;
  /** Rendered after the Run button (e.g. Save + status) and before scan/delete results. */
  afterRunSlot?: ReactNode;
};

async function evaluateEligibilityForSnapshots(
  instanceId: number,
  mediaScope: "tv" | "movies",
  snaps: PreviewSnapshot[],
): Promise<{
  elig: Record<string, boolean>;
  reasons: Record<string, string[]>;
}> {
  const elig: Record<string, boolean> = {};
  const reasons: Record<string, string[]> = {};
  for (const s of snaps) {
    if (s.outcome !== "success" || s.rows.length === 0) continue;
    try {
      const r = await fetchPrunerApplyEligibility(
        instanceId,
        mediaScope,
        s.previewRunId,
      );
      elig[s.previewRunId] = r.eligible;
      reasons[s.previewRunId] = r.reasons;
    } catch {
      elig[s.previewRunId] = false;
      reasons[s.previewRunId] = [
        "Could not confirm whether these items can be deleted safely.",
      ];
    }
  }
  return { elig, reasons };
}

/** Review-snapshot button and scan results for one media column. */
export function PrunerDryRunControls(props: PrunerDryRunControlsProps) {
  const {
    instanceId,
    mediaScope,
    testIdPrefix,
    ensureSaved,
    dryRunEnabled,
    onDryRunEnabledChange,
    runDisabled,
    controlsDisabled,
    afterRunSlot,
  } = props;
  const qc = useQueryClient();
  void onDryRunEnabledChange;
  const [phase, setPhase] = useState<
    "idle" | "scanning" | "results" | "deleting"
  >("idle");
  const [err, setErr] = useState<string | null>(null);
  const [snapshots, setSnapshots] = useState<PreviewSnapshot[]>([]);
  const [deleteEligible, setDeleteEligible] = useState<Record<string, boolean>>(
    {},
  );
  const [deleteReasons, setDeleteReasons] = useState<Record<string, string[]>>(
    {},
  );
  const [applySummary, setApplySummary] = useState<string | null>(null);

  const allRows = useMemo(() => {
    const rows: CandidateDisplayRow[] = [];
    for (const s of snapshots) {
      rows.push(...s.rows);
    }
    return rows;
  }, [snapshots]);

  const totalCount = allRows.length;
  const [emptyBecauseNoRules, setEmptyBecauseNoRules] = useState(false);

  async function runCleanupNow() {
    setErr(null);
    setApplySummary(null);
    setSnapshots([]);
    setDeleteEligible({});
    setDeleteReasons({});
    setPhase("scanning");
    setEmptyBecauseNoRules(false);
    try {
      await ensureSaved();
      await qc.invalidateQueries({
        queryKey: ["pruner", "instances", instanceId],
      });
      const fresh = await fetchPrunerInstance(instanceId);
      const tv = scopeRow(fresh, "tv");
      const movies = scopeRow(fresh, "movies");
      if (!tv || !movies) {
        throw new Error(
          "TV and movie settings for this server are missing. Try reloading the page.",
        );
      }
      const families =
        mediaScope === "tv"
          ? tvRuleFamiliesToScan(fresh.provider, tv)
          : moviesRuleFamiliesToScan(movies);
      if (families.length === 0) {
        setSnapshots([]);
        setEmptyBecauseNoRules(true);
        setPhase("results");
        return;
      }
      const collected: PreviewSnapshot[] = [];
      for (const ruleFamilyId of families) {
        const { pruner_job_id } = await postPrunerPreview(
          instanceId,
          mediaScope,
          { rule_family_id: ruleFamilyId },
        );
        let terminal: "completed" | "failed";
        try {
          terminal = await waitForPrunerJobTerminal(pruner_job_id, {
            pollMs: PRUNER_SCAN_POLL_MS,
            timeoutMs: PRUNER_SCAN_TIMEOUT_MS,
          });
        } catch {
          setErr(
            "Scan is taking longer than expected. Check Activity for results.",
          );
          setPhase("idle");
          return;
        }
        if (terminal === "failed") {
          setErr("Library scan failed. Check Activity for details.");
          setPhase("idle");
          return;
        }
        const previewRunId = await resolvePreviewRunIdForJob(
          instanceId,
          mediaScope,
          pruner_job_id,
          {
            pollMs: PRUNER_SCAN_POLL_MS,
            timeoutMs: PRUNER_SCAN_TIMEOUT_MS,
          },
        );
        if (!previewRunId) {
          setErr(
            "Scan is taking longer than expected. Check Activity for results.",
          );
          setPhase("idle");
          return;
        }
        const run = await fetchPrunerPreviewRun(instanceId, previewRunId);
        const label = ruleFamilyOperatorLabel(run.rule_family_id);
        const parsed = parseCandidatesJsonArray(run.candidates_json);
        const rows = displayRowsForCandidates(parsed, label);
        collected.push({
          previewRunId: run.preview_run_id,
          ruleFamilyId: run.rule_family_id,
          ruleLabel: label,
          rows,
          truncated: run.truncated,
          unsupportedDetail: run.unsupported_detail,
          errorMessage: run.error_message,
          outcome: run.outcome,
        });
      }

      const { elig, reasons } = await evaluateEligibilityForSnapshots(
        instanceId,
        mediaScope,
        collected,
      );
      setSnapshots(collected);
      setDeleteEligible(elig);
      setDeleteReasons(reasons);

      const rowsCount = collected.reduce((acc, s) => acc + s.rows.length, 0);
      const eligibleAny = collected.some(
        (s) =>
          s.outcome === "success" &&
          s.rows.length > 0 &&
          elig[s.previewRunId] === true,
      );

      if (dryRunEnabled) {
        setPhase("results");
        await qc.invalidateQueries({
          queryKey: ["pruner", "instances", instanceId],
        });
        return;
      }

      if (rowsCount === 0) {
        setPhase("results");
        await qc.invalidateQueries({
          queryKey: ["pruner", "instances", instanceId],
        });
        return;
      }

      if (!eligibleAny) {
        setPhase("results");
        await qc.invalidateQueries({
          queryKey: ["pruner", "instances", instanceId],
        });
        return;
      }

      setPhase("deleting");
      let removed = 0;
      let skipped = 0;
      let failed = 0;
      for (const s of collected) {
        if (s.outcome !== "success" || s.rows.length === 0) continue;
        if (!elig[s.previewRunId]) continue;
        const { pruner_job_id } = await postPrunerApplyFromPreview(
          instanceId,
          mediaScope,
          s.previewRunId,
        );
        try {
          await waitForPrunerJobTerminal(pruner_job_id, {
            pollMs: PRUNER_SCAN_POLL_MS,
            timeoutMs: PRUNER_SCAN_TIMEOUT_MS,
          });
        } catch {
          setApplySummary(
            "Delete is taking longer than expected. Check Activity — your server may still be processing items.",
          );
          setPhase("results");
          await qc.invalidateQueries({
            queryKey: ["pruner", "instances", instanceId],
          });
          await qc.invalidateQueries({ queryKey: ["activity"] });
          return;
        }
        const parsed = await waitForApplyActivity(s.previewRunId, {
          pollMs: PRUNER_SCAN_POLL_MS,
          timeoutMs: PRUNER_SCAN_TIMEOUT_MS,
        });
        removed += parsed?.removed ?? 0;
        skipped += parsed?.skipped ?? 0;
        failed += parsed?.failed ?? 0;
      }
      setSnapshots([]);
      setDeleteEligible({});
      setDeleteReasons({});
      setApplySummary(
        `Deleted ${removed} items. Skipped ${skipped}. Failed ${failed}.`,
      );
      setPhase("results");
      await qc.invalidateQueries({
        queryKey: ["pruner", "instances", instanceId],
      });
      await qc.invalidateQueries({ queryKey: ["activity"] });
    } catch (e) {
      setErr((e as Error).message);
      setPhase("idle");
    }
  }

  const runLabel =
    mediaScope === "tv"
      ? "Scan TV for cleanup review"
      : "Scan Movies for cleanup review";
  const runBusy = phase === "scanning" || phase === "deleting";
  const runBtnDisabled = runDisabled || controlsDisabled || runBusy;

  return (
    <div
      className="min-w-0 space-y-4"
      data-testid={`${testIdPrefix}-run-${mediaScope}`}
    >
      <p className="text-xs text-[var(--mm-text3)]">
        This scans your saved rules and creates a review snapshot. Nothing is
        deleted from this button; deletion only happens when you open and
        confirm a saved snapshot.
      </p>
      <div>
        <button
          type="button"
          className={mmActionButtonClass({
            variant: "primary",
            disabled: runBtnDisabled,
          })}
          disabled={runBtnDisabled}
          data-testid={`${testIdPrefix}-run-${mediaScope}-btn`}
          onClick={() => void runCleanupNow()}
        >
          {phase === "scanning" ? "Scanning…" : runLabel}
        </button>
      </div>
      {afterRunSlot ? <div className="space-y-3">{afterRunSlot}</div> : null}
      {err ? (
        <p className="text-sm text-red-500" role="alert">
          {err}
        </p>
      ) : null}
      <PrunerDryRunResults
        phase={phase}
        err={err}
        emptyBecauseNoRules={emptyBecauseNoRules}
        dryRunEnabled={dryRunEnabled}
        snapshots={snapshots}
        totalCount={totalCount}
        allRows={allRows}
        deleteEligible={deleteEligible}
        deleteReasons={deleteReasons}
        applySummary={applySummary}
      />
    </div>
  );
}

