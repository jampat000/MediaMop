import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchCsrfToken } from "../../lib/api/auth-api";
import { useMeQuery } from "../../lib/auth/queries";
import {
  PRUNER_REMOVE_BROKEN_LIBRARY_ENTRIES_LABEL,
  fetchPrunerApplyEligibility,
  fetchPrunerPreviewRun,
  fetchPrunerPreviewRuns,
  patchPrunerScope,
  postPrunerApplyFromPreview,
  postPrunerPreview,
} from "../../lib/pruner/api";
import type { PrunerServerInstance } from "../../lib/pruner/api";

type Ctx = { instanceId: number; instance: PrunerServerInstance | undefined };

export function PrunerScopeTab(props: { scope: "tv" | "movies" }) {
  const { instanceId, instance } = useOutletContext<Ctx>();
  const me = useMeQuery();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [jsonPreview, setJsonPreview] = useState<string | null>(null);
  const [schedEnabled, setSchedEnabled] = useState(false);
  const [schedInterval, setSchedInterval] = useState(3600);
  const [schedMsg, setSchedMsg] = useState<string | null>(null);
  const [applyModalRunId, setApplyModalRunId] = useState<string | null>(null);
  const [applySnapshotConfirmed, setApplySnapshotConfirmed] = useState(false);
  const canOperate = me.data?.role === "admin" || me.data?.role === "operator";

  const scopeRow = instance?.scopes.find((s) => s.media_scope === props.scope);
  const label = props.scope === "tv" ? "TV (episodes)" : "Movies (one row per movie item)";
  const isPlex = instance?.provider === "plex";
  const isJellyfin = instance?.provider === "jellyfin";

  const previewRunsQueryKey = ["pruner", "preview-runs", instanceId, props.scope] as const;
  const runsQuery = useQuery({
    queryKey: previewRunsQueryKey,
    queryFn: () => fetchPrunerPreviewRuns(instanceId, { media_scope: props.scope, limit: 25 }),
    enabled: Boolean(instanceId),
  });

  const applyEligQuery = useQuery({
    queryKey: ["pruner", "apply-eligibility", instanceId, props.scope, applyModalRunId] as const,
    queryFn: () => fetchPrunerApplyEligibility(instanceId, props.scope, applyModalRunId!),
    enabled: Boolean(instanceId && applyModalRunId),
  });

  useEffect(() => {
    if (!scopeRow) return;
    setSchedEnabled(scopeRow.scheduled_preview_enabled);
    setSchedInterval(scopeRow.scheduled_preview_interval_seconds);
  }, [
    scopeRow?.scheduled_preview_enabled,
    scopeRow?.scheduled_preview_interval_seconds,
    scopeRow?.media_scope,
    instanceId,
  ]);

  async function saveSchedule() {
    setSchedMsg(null);
    setErr(null);
    setBusy(true);
    try {
      const csrf_token = await fetchCsrfToken();
      const iv = Math.max(60, Math.min(86400, Number(schedInterval) || 3600));
      await patchPrunerScope(instanceId, props.scope, {
        scheduled_preview_enabled: schedEnabled,
        scheduled_preview_interval_seconds: iv,
        csrf_token,
      });
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      setSchedMsg("Saved. This schedule applies only to this server and this tab (TV or Movies).");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function runPreview() {
    setErr(null);
    setBusy(true);
    setPreview(null);
    try {
      const { pruner_job_id } = await postPrunerPreview(instanceId, props.scope);
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      await qc.invalidateQueries({ queryKey: previewRunsQueryKey });
      setPreview(
        `Queued preview job #${pruner_job_id}. When the worker finishes, the summary above and the recent-run table update automatically (this scope only).`,
      );
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function openApplyModal(runUuid: string) {
    setApplySnapshotConfirmed(false);
    setApplyModalRunId(runUuid);
  }

  function closeApplyModal() {
    setApplyModalRunId(null);
    setApplySnapshotConfirmed(false);
  }

  async function confirmApplyFromSnapshot() {
    if (!applyModalRunId) return;
    const runId = applyModalRunId;
    setErr(null);
    setBusy(true);
    try {
      const { pruner_job_id } = await postPrunerApplyFromPreview(instanceId, props.scope, runId);
      await qc.invalidateQueries({ queryKey: previewRunsQueryKey });
      await qc.invalidateQueries({ queryKey: ["activity"] });
      closeApplyModal();
      setPreview(
        `Queued ${PRUNER_REMOVE_BROKEN_LIBRARY_ENTRIES_LABEL.toLowerCase()} job #${pruner_job_id} for preview snapshot ${runId.slice(0, 8)}… (this preview only; worker runs separately).`,
      );
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function loadJsonFor(runUuid?: string | null) {
    const uuid = runUuid ?? scopeRow?.last_preview_run_uuid;
    if (!uuid) {
      setErr("No preview run selected.");
      return;
    }
    setErr(null);
    setBusy(true);
    setJsonPreview(null);
    try {
      const run = await fetchPrunerPreviewRun(instanceId, uuid);
      setJsonPreview(run.candidates_json);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="max-w-3xl space-y-3" aria-labelledby="pruner-scope-heading">
      <h2 id="pruner-scope-heading" className="text-base font-semibold text-[var(--mm-text)]">
        {label}
      </h2>
      <p className="text-sm text-[var(--mm-text2)]">
        {props.scope === "tv"
          ? "Previews list episodes missing a primary image (episode-level rows only)."
          : "Previews list movie items missing a primary image (one candidate row per movie library item)."}
      </p>
      {isPlex ? (
        <div
          className="rounded-md border border-amber-600/40 bg-amber-950/20 px-3 py-2 text-sm text-[var(--mm-text)]"
          role="status"
        >
          Plex: missing-primary preview is <strong>not supported</strong> in this release (the API records an explicit{" "}
          <code className="text-[0.85em]">unsupported</code> outcome after the job runs). Use the Connection tab for a
          real Plex ping.
        </div>
      ) : null}
      {scopeRow ? (
        <div className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text2)]">
          <div>Last outcome: {scopeRow.last_preview_outcome ?? "—"}</div>
          <div>Last candidate count: {scopeRow.last_preview_candidate_count ?? "—"}</div>
          <div>Last error: {scopeRow.last_preview_error ?? "—"}</div>
        </div>
      ) : null}
      {canOperate ? (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-md bg-[var(--mm-accent)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            disabled={busy || isPlex}
            title={isPlex ? "Preview unsupported for Plex in this release." : undefined}
            onClick={() => void runPreview()}
          >
            Queue preview job
          </button>
          <button
            type="button"
            className="rounded-md border border-[var(--mm-border)] px-3 py-1.5 text-sm font-medium text-[var(--mm-text)] disabled:opacity-50"
            disabled={busy || !scopeRow?.last_preview_run_uuid}
            onClick={() => void loadJsonFor(scopeRow?.last_preview_run_uuid)}
          >
            Load candidates JSON (latest summary)
          </button>
        </div>
      ) : (
        <p className="text-sm text-[var(--mm-text2)]">Sign in as an operator to queue previews.</p>
      )}
      <div
        className="space-y-2 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3"
        data-testid="pruner-scope-scheduled-preview"
      >
        <h3 className="text-sm font-semibold text-[var(--mm-text)]">Scheduled preview ({props.scope})</h3>
        <p className="text-xs text-[var(--mm-text2)]">
          Each server instance has separate TV and Movies schedules. Interval: 60 seconds to 24 hours. The timestamp
          below updates only when the background scheduler queues a job for this tab — not when you use &quot;Queue
          preview job&quot;.
        </p>
        {canOperate ? (
          <>
            <label className="flex items-center gap-2 text-sm text-[var(--mm-text)]">
              <input
                type="checkbox"
                checked={schedEnabled}
                disabled={busy}
                onChange={(e) => setSchedEnabled(e.target.checked)}
              />
              Enable scheduled previews for this tab
            </label>
            <div className="flex flex-wrap items-center gap-2">
              <label className="text-sm text-[var(--mm-text2)]">
                Every{" "}
                <input
                  type="number"
                  min={60}
                  max={86400}
                  className="w-28 rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-1 text-sm text-[var(--mm-text)]"
                  value={schedInterval}
                  disabled={busy}
                  onChange={(e) => setSchedInterval(parseInt(e.target.value, 10) || 3600)}
                />{" "}
                seconds
              </label>
              <button
                type="button"
                className="rounded-md bg-[var(--mm-accent)] px-3 py-1 text-sm font-medium text-white disabled:opacity-50"
                disabled={busy}
                onClick={() => void saveSchedule()}
              >
                Save schedule
              </button>
            </div>
            {schedMsg ? <p className="text-xs text-green-600">{schedMsg}</p> : null}
          </>
        ) : (
          <p className="text-sm text-[var(--mm-text2)]">
            Scheduled preview is <strong>{scopeRow?.scheduled_preview_enabled ? "on" : "off"}</strong>
            {scopeRow ? (
              <>
                {" "}
                (every {scopeRow.scheduled_preview_interval_seconds}s). Sign in as an operator to change it.
              </>
            ) : null}
          </p>
        )}
        <p className="text-xs text-[var(--mm-text2)]">
          Last scheduled enqueue:{" "}
          {scopeRow?.last_scheduled_preview_enqueued_at
            ? new Date(scopeRow.last_scheduled_preview_enqueued_at).toLocaleString()
            : "—"}
        </p>
      </div>
      <div className="space-y-2" data-testid="pruner-preview-runs-history">
        <h3 className="text-sm font-semibold text-[var(--mm-text)]">Recent preview runs ({props.scope})</h3>
        {runsQuery.isLoading ? (
          <p className="text-sm text-[var(--mm-text2)]">Loading history…</p>
        ) : runsQuery.isError ? (
          <p className="text-sm text-red-600" role="alert">
            {(runsQuery.error as Error).message}
          </p>
        ) : runsQuery.data?.length ? (
          <div className="overflow-x-auto rounded-md border border-[var(--mm-border)]">
            <table className="w-full min-w-[32rem] border-collapse text-left text-sm text-[var(--mm-text)]">
              <thead className="border-b border-[var(--mm-border)] bg-[var(--mm-surface2)] text-xs uppercase text-[var(--mm-text2)]">
                <tr>
                  <th className="px-2 py-2">Run</th>
                  <th className="px-2 py-2">When</th>
                  <th className="px-2 py-2">Outcome</th>
                  <th className="px-2 py-2">Candidates</th>
                  <th className="px-2 py-2"> </th>
                </tr>
              </thead>
              <tbody>
                {runsQuery.data.map((row) => (
                  <tr key={row.preview_run_id} className="border-b border-[var(--mm-border)] align-top">
                    <td className="px-2 py-2 font-mono text-xs">{row.preview_run_id.slice(0, 8)}…</td>
                    <td className="px-2 py-2 text-xs text-[var(--mm-text2)]">
                      {new Date(row.created_at).toLocaleString()}
                    </td>
                    <td className="px-2 py-2 text-xs">
                      <span className="font-medium">{row.outcome}</span>
                      {row.unsupported_detail ? (
                        <div className="mt-1 text-[var(--mm-text2)]">{row.unsupported_detail}</div>
                      ) : null}
                      {row.error_message ? (
                        <div className="mt-1 text-red-600">{row.error_message}</div>
                      ) : null}
                    </td>
                    <td className="px-2 py-2 text-xs">
                      {row.candidate_count}
                      {row.truncated ? " (truncated)" : ""}
                    </td>
                    <td className="px-2 py-2 space-y-1">
                      <button
                        type="button"
                        className="rounded border border-[var(--mm-border)] px-2 py-1 text-xs font-medium text-[var(--mm-text)] disabled:opacity-50"
                        disabled={busy}
                        onClick={() => void loadJsonFor(row.preview_run_id)}
                      >
                        JSON
                      </button>
                      {canOperate && isJellyfin && row.outcome === "success" && row.candidate_count > 0 ? (
                        <div>
                          <button
                            type="button"
                            className="mt-1 block w-full rounded border border-red-900/50 bg-red-950/30 px-2 py-1 text-left text-xs font-medium text-red-100 disabled:opacity-50"
                            data-testid={`pruner-apply-open-${row.preview_run_id}`}
                            disabled={busy}
                            onClick={() => openApplyModal(row.preview_run_id)}
                          >
                            {PRUNER_REMOVE_BROKEN_LIBRARY_ENTRIES_LABEL}
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
          <p className="text-sm text-[var(--mm-text2)]">No preview runs recorded for this scope yet.</p>
        )}
      </div>
      {applyModalRunId ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="pruner-apply-modal-title"
          data-testid="pruner-apply-modal"
        >
          <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-4 shadow-xl">
            <h3 id="pruner-apply-modal-title" className="text-base font-semibold text-[var(--mm-text)]">
              {PRUNER_REMOVE_BROKEN_LIBRARY_ENTRIES_LABEL}
            </h3>
            <p className="mt-2 text-sm text-[var(--mm-text2)]">
              This live action uses <strong>only</strong> the frozen candidate list from one preview snapshot. It does
              not re-run preview and does not widen the candidate set.
            </p>
            {applyEligQuery.isLoading ? (
              <p className="mt-3 text-sm text-[var(--mm-text2)]">Checking eligibility…</p>
            ) : applyEligQuery.isError ? (
              <p className="mt-3 text-sm text-red-600" role="alert">
                {(applyEligQuery.error as Error).message}
              </p>
            ) : applyEligQuery.data ? (
              <ul className="mt-3 list-inside list-disc space-y-1 text-sm text-[var(--mm-text)]">
                <li>
                  Server: <strong>{applyEligQuery.data.display_name}</strong> ({applyEligQuery.data.provider})
                </li>
                <li>
                  Scope: <strong>{applyEligQuery.data.media_scope === "tv" ? "TV" : "Movies"}</strong>
                </li>
                <li>
                  Preview time:{" "}
                  {applyEligQuery.data.preview_created_at
                    ? new Date(applyEligQuery.data.preview_created_at).toLocaleString()
                    : "—"}
                </li>
                <li>
                  Snapshot id: <span className="font-mono text-xs">{applyEligQuery.data.preview_run_id}</span>
                </li>
                <li>
                  Candidates in snapshot: <strong>{applyEligQuery.data.candidate_count}</strong>
                </li>
              </ul>
            ) : null}
            {applyEligQuery.data && !applyEligQuery.data.eligible ? (
              <p className="mt-3 text-sm text-amber-700" role="status">
                {applyEligQuery.data.reasons.length
                  ? applyEligQuery.data.reasons.join(" ")
                  : "This snapshot cannot be applied right now."}
              </p>
            ) : null}
            {applyEligQuery.data?.eligible ? (
              <label className="mt-4 flex cursor-pointer items-start gap-2 text-sm text-[var(--mm-text)]">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={applySnapshotConfirmed}
                  onChange={(e) => setApplySnapshotConfirmed(e.target.checked)}
                />
                <span>
                  I confirm <strong>{PRUNER_REMOVE_BROKEN_LIBRARY_ENTRIES_LABEL}</strong> for this exact preview
                  snapshot only ({applyModalRunId.slice(0, 8)}…), with at most {applyEligQuery.data.candidate_count}{" "}
                  library entries.
                </span>
              </label>
            ) : null}
            <div className="mt-4 flex flex-wrap justify-end gap-2">
              <button
                type="button"
                className="rounded-md border border-[var(--mm-border)] px-3 py-1.5 text-sm font-medium text-[var(--mm-text)]"
                onClick={() => closeApplyModal()}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded-md bg-red-800 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                data-testid="pruner-apply-confirm"
                disabled={
                  busy ||
                  !applyEligQuery.data?.eligible ||
                  !applySnapshotConfirmed ||
                  applyEligQuery.isLoading ||
                  applyEligQuery.isError
                }
                onClick={() => void confirmApplyFromSnapshot()}
              >
                {PRUNER_REMOVE_BROKEN_LIBRARY_ENTRIES_LABEL}
              </button>
            </div>
          </div>
        </div>
      ) : null}
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
    </section>
  );
}
