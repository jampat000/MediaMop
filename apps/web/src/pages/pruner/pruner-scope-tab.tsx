import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchCsrfToken } from "../../lib/api/auth-api";
import { useMeQuery } from "../../lib/auth/queries";
import {
  PRUNER_REMOVE_BROKEN_LIBRARY_ENTRIES_LABEL,
  RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED,
  RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED,
  fetchPrunerApplyEligibility,
  fetchPrunerPlexLiveEligibility,
  fetchPrunerPreviewRun,
  fetchPrunerPreviewRuns,
  patchPrunerScope,
  postPrunerApplyFromPreview,
  postPrunerPlexLiveRemoval,
  postPrunerPreview,
  prunerApplyLabelForRuleFamily,
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
  const [plexLiveOpen, setPlexLiveOpen] = useState(false);
  const [plexNoPreviewAck, setPlexNoPreviewAck] = useState(false);
  const [plexLiveAck, setPlexLiveAck] = useState(false);
  const [plexTypedPhrase, setPlexTypedPhrase] = useState("");
  const [staleNeverEnabled, setStaleNeverEnabled] = useState(false);
  const [staleNeverDays, setStaleNeverDays] = useState(90);
  const [staleNeverMsg, setStaleNeverMsg] = useState<string | null>(null);
  const canOperate = me.data?.role === "admin" || me.data?.role === "operator";

  const scopeRow = instance?.scopes.find((s) => s.media_scope === props.scope);
  const label = props.scope === "tv" ? "TV (episodes)" : "Movies (one row per movie item)";
  const isPlex = instance?.provider === "plex";
  const canApplyJfEmbyFromSnapshot = instance?.provider === "jellyfin" || instance?.provider === "emby";

  function ruleFamilyColumnLabel(id: string): string {
    if (id === RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED) return "Stale never-played";
    if (id === RULE_FAMILY_MISSING_PRIMARY_MEDIA_REPORTED) return "Missing primary art";
    return id;
  }

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

  const applySnapshotOperatorLabel = applyEligQuery.data
    ? applyEligQuery.data.apply_operator_label ||
      prunerApplyLabelForRuleFamily(applyEligQuery.data.rule_family_id)
    : null;

  const plexLiveEligQuery = useQuery({
    queryKey: ["pruner", "plex-live-eligibility", instanceId, props.scope] as const,
    queryFn: () => fetchPrunerPlexLiveEligibility(instanceId, props.scope),
    enabled: Boolean(isPlex && instanceId),
  });

  useEffect(() => {
    if (!scopeRow) return;
    setSchedEnabled(scopeRow.scheduled_preview_enabled);
    setSchedInterval(scopeRow.scheduled_preview_interval_seconds);
    setStaleNeverEnabled(scopeRow.never_played_stale_reported_enabled);
    setStaleNeverDays(scopeRow.never_played_min_age_days);
  }, [
    scopeRow?.scheduled_preview_enabled,
    scopeRow?.scheduled_preview_interval_seconds,
    scopeRow?.never_played_stale_reported_enabled,
    scopeRow?.never_played_min_age_days,
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

  async function saveStaleNeverSettings() {
    setStaleNeverMsg(null);
    setErr(null);
    setBusy(true);
    try {
      const csrf_token = await fetchCsrfToken();
      const d = Math.max(7, Math.min(3650, Number(staleNeverDays) || 90));
      await patchPrunerScope(instanceId, props.scope, {
        never_played_stale_reported_enabled: staleNeverEnabled,
        never_played_min_age_days: d,
        csrf_token,
      });
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      setStaleNeverMsg("Saved never-played rule settings for this tab only.");
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
        `Queued missing-primary preview job #${pruner_job_id}. When the worker finishes, the summary above and the recent-run table update automatically (this scope only).`,
      );
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function runStaleNeverPreview() {
    setErr(null);
    setBusy(true);
    setPreview(null);
    try {
      const { pruner_job_id } = await postPrunerPreview(instanceId, props.scope, {
        rule_family_id: RULE_FAMILY_NEVER_PLAYED_STALE_REPORTED,
      });
      await qc.invalidateQueries({ queryKey: ["pruner", "instances", instanceId] });
      await qc.invalidateQueries({ queryKey: previewRunsQueryKey });
      setPreview(
        `Queued never-played stale preview job #${pruner_job_id}. When the worker finishes, the table below updates (this scope only).`,
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

  function openPlexLiveModal() {
    setPlexNoPreviewAck(false);
    setPlexLiveAck(false);
    setPlexTypedPhrase("");
    setPlexLiveOpen(true);
    void qc.invalidateQueries({ queryKey: ["pruner", "plex-live-eligibility", instanceId, props.scope] });
  }

  function closePlexLiveModal() {
    setPlexLiveOpen(false);
    setPlexNoPreviewAck(false);
    setPlexLiveAck(false);
    setPlexTypedPhrase("");
  }

  async function confirmPlexLiveRemoval() {
    setErr(null);
    setBusy(true);
    try {
      const { pruner_job_id } = await postPrunerPlexLiveRemoval(instanceId, props.scope, {
        live_removal_confirmation: plexTypedPhrase.trim(),
      });
      await qc.invalidateQueries({ queryKey: ["pruner", "plex-live-eligibility", instanceId, props.scope] });
      await qc.invalidateQueries({ queryKey: ["activity"] });
      closePlexLiveModal();
      setPreview(
        `Queued Plex live ${PRUNER_REMOVE_BROKEN_LIBRARY_ENTRIES_LABEL.toLowerCase()} job #${pruner_job_id} for this server and ${props.scope} tab only (no preview; worker runs separately).`,
      );
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function confirmApplyFromSnapshot() {
    if (!applyModalRunId) return;
    const runId = applyModalRunId;
    const elig = applyEligQuery.data;
    if (!elig) return;
    const opLabel =
      elig.apply_operator_label || prunerApplyLabelForRuleFamily(elig.rule_family_id);
    setErr(null);
    setBusy(true);
    try {
      const { pruner_job_id } = await postPrunerApplyFromPreview(instanceId, props.scope, runId);
      await qc.invalidateQueries({ queryKey: previewRunsQueryKey });
      await qc.invalidateQueries({ queryKey: ["activity"] });
      closeApplyModal();
      setPreview(
        `Queued ${opLabel.toLowerCase()} job #${pruner_job_id} for preview snapshot ${runId.slice(0, 8)}… (this preview only; worker runs separately).`,
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
      {!isPlex ? (
        <p className="text-sm text-[var(--mm-text2)]">
          {props.scope === "tv"
            ? "Previews list episodes missing a primary image (episode-level rows only), or episodes that are unplayed for the MediaMop token and older than your age threshold by library DateCreated — each rule has its own preview queue."
            : "Previews list movie items missing a primary image (one row per movie), or movies that are unplayed for the MediaMop token and older than your age threshold by library DateCreated — each rule has its own preview queue."}
        </p>
      ) : (
        <p className="text-sm text-[var(--mm-text2)]">
          <strong>Jellyfin and Emby</strong> use preview here: items missing a primary image (
          {props.scope === "tv" ? "episode-level rows" : "one row per movie item"}).{" "}
          <strong>Plex</strong> does not use preview for this rule on this tab — only the live removal path below.
        </p>
      )}
      {isPlex ? (
        <div className="space-y-3">
          <div
            className="rounded-md border border-amber-600/40 bg-amber-950/20 px-3 py-2 text-sm text-[var(--mm-text)]"
            role="status"
          >
            <p className="font-medium text-amber-100">Plex (this rule family)</p>
            <p className="mt-1 text-[var(--mm-text2)]">
              There is <strong>no preview and no dry run</strong> for Remove broken library entries on Plex. The only
              supported path here is a <strong>live</strong> job: MediaMop scans Plex at job time (up to your per-scope
              cap) and issues live deletes — it is <strong>not</strong> tied to a preview snapshot.
            </p>
            <p className="mt-2 text-xs text-[var(--mm-text2)]">
              Plex detection uses provider-specific metadata (empty/missing <code className="text-[0.85em]">thumb</code>{" "}
              on the leaf item). That is <strong>not</strong> the same signal as Jellyfin/Emby primary-image preview.
              MediaMop does <strong>not</strong> claim whether Plex removes only metadata or also media files — that
              depends on your Plex server.
            </p>
            <p className="mt-2 text-xs text-[var(--mm-text2)]">
              Scheduled &quot;preview&quot; jobs for Plex still record an explicit unsupported outcome (connection test
              remains on the Connection tab).
            </p>
            <p className="mt-2 text-xs text-[var(--mm-text2)]">
              The stale never-played rule is <strong>not</strong> available for Plex on this tab — there is no honest
              preview path for it here.
            </p>
          </div>
          {canOperate ? (
            <div
              className="rounded-md border border-red-900/40 bg-red-950/20 px-3 py-2 text-sm text-[var(--mm-text)]"
              data-testid="pruner-plex-live-surface"
            >
              <p className="font-medium text-red-100">{PRUNER_REMOVE_BROKEN_LIBRARY_ENTRIES_LABEL} (Plex live)</p>
              {plexLiveEligQuery.isLoading ? (
                <p className="mt-2 text-xs text-[var(--mm-text2)]">Checking gates…</p>
              ) : plexLiveEligQuery.isError ? (
                <p className="mt-2 text-xs text-red-400" role="alert">
                  {(plexLiveEligQuery.error as Error).message}
                </p>
              ) : plexLiveEligQuery.data ? (
                <div className="mt-2 space-y-1 text-xs text-[var(--mm-text2)]">
                  <div>
                    Apply gate (MEDIAMOP_PRUNER_APPLY_ENABLED):{" "}
                    <strong>{plexLiveEligQuery.data.apply_feature_enabled ? "on" : "off"}</strong>
                  </div>
                  <div>
                    Plex live gate (MEDIAMOP_PRUNER_PLEX_LIVE_REMOVAL_ENABLED):{" "}
                    <strong>{plexLiveEligQuery.data.plex_live_feature_enabled ? "on" : "off"}</strong>
                  </div>
                  <div>
                    Rule enabled for this tab: <strong>{plexLiveEligQuery.data.rule_enabled ? "yes" : "no"}</strong>
                  </div>
                  <div>
                    Live cap for this run (min of per-scope item cap and server absolute cap):{" "}
                    <strong>{plexLiveEligQuery.data.live_max_items_cap}</strong>
                  </div>
                  {!plexLiveEligQuery.data.eligible ? (
                    <p className="pt-1 text-amber-200">{plexLiveEligQuery.data.reasons.join(" ")}</p>
                  ) : null}
                </div>
              ) : null}
              <button
                type="button"
                className="mt-3 rounded-md border border-red-800/60 bg-red-950/40 px-3 py-1.5 text-sm font-medium text-red-50 disabled:opacity-50"
                data-testid="pruner-plex-live-open"
                disabled={busy || !plexLiveEligQuery.data?.eligible}
                title={!plexLiveEligQuery.data?.eligible ? "Fix eligibility issues above before continuing." : undefined}
                onClick={() => openPlexLiveModal()}
              >
                {PRUNER_REMOVE_BROKEN_LIBRARY_ENTRIES_LABEL} (live)…
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
      {!isPlex ? (
        <div
          className="space-y-3 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
          data-testid="pruner-never-played-stale-panel"
        >
          <p className="text-sm font-semibold text-[var(--mm-text)]">Stale never-played (Jellyfin / Emby)</p>
          <p className="text-xs text-[var(--mm-text2)]">
            Candidates are library items with <strong>no play state</strong> for the MediaMop server user (Jellyfin /
            Emby user data) and a <strong>DateCreated</strong> older than the minimum age below. This tab (TV or
            Movies) and this server instance only — nothing global.
          </p>
          <p className="text-xs text-[var(--mm-text2)]">
            Apply (when enabled) removes those library entries via the provider API for the frozen preview list only —
            MediaMop does not claim whether underlying media files are deleted; that is provider behavior.
          </p>
          {canOperate ? (
            <div className="space-y-2">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={staleNeverEnabled}
                  disabled={busy}
                  onChange={(e) => setStaleNeverEnabled(e.target.checked)}
                />
                Enable stale never-played rule for this tab
              </label>
              <div className="flex flex-wrap items-center gap-2">
                <label className="text-sm text-[var(--mm-text2)]">
                  Minimum age (days, 7–3650):{" "}
                  <input
                    type="number"
                    min={7}
                    max={3650}
                    className="w-24 rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-1 text-sm text-[var(--mm-text)]"
                    value={staleNeverDays}
                    disabled={busy}
                    onChange={(e) => setStaleNeverDays(parseInt(e.target.value, 10) || 90)}
                  />
                </label>
                <button
                  type="button"
                  className="rounded-md border border-[var(--mm-border)] px-3 py-1 text-sm font-medium text-[var(--mm-text)] disabled:opacity-50"
                  disabled={busy}
                  onClick={() => void saveStaleNeverSettings()}
                >
                  Save never-played rule
                </button>
              </div>
              {staleNeverMsg ? <p className="text-xs text-green-600">{staleNeverMsg}</p> : null}
              <button
                type="button"
                className="rounded-md bg-[var(--mm-surface2)] px-3 py-1.5 text-sm font-medium text-[var(--mm-text)] ring-1 ring-[var(--mm-border)] disabled:opacity-50"
                disabled={busy || !staleNeverEnabled}
                title={!staleNeverEnabled ? "Enable the rule and save before queueing a preview for it." : undefined}
                onClick={() => void runStaleNeverPreview()}
              >
                Queue preview (stale never-played)
              </button>
            </div>
          ) : (
            <p className="text-xs text-[var(--mm-text2)]">
              Rule is <strong>{scopeRow?.never_played_stale_reported_enabled ? "on" : "off"}</strong>
              {scopeRow ? (
                <>
                  {" "}
                  (minimum age {scopeRow.never_played_min_age_days} days). Sign in as an operator to change it.
                </>
              ) : null}
            </p>
          )}
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
            title={
              isPlex
                ? "No preview for Plex on this rule — use the live removal panel above, not this button."
                : undefined
            }
            onClick={() => void runPreview()}
          >
            Queue preview (missing primary art)
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
          below updates only when the background scheduler queues a job for this tab — not when you use the manual
          preview buttons. Scheduled runs use the <strong>missing primary art</strong> rule only; stale never-played
          previews are on-demand.
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
                  <th className="px-2 py-2">Rule</th>
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
                    <td className="px-2 py-2 text-xs text-[var(--mm-text2)]">{ruleFamilyColumnLabel(row.rule_family_id)}</td>
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
                      {canOperate && canApplyJfEmbyFromSnapshot && row.outcome === "success" && row.candidate_count > 0 ? (
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
              {applySnapshotOperatorLabel ?? "Apply from preview snapshot"}
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
                  I confirm <strong>{applySnapshotOperatorLabel}</strong> for this exact preview snapshot only (
                  {applyModalRunId.slice(0, 8)}…), with at most {applyEligQuery.data.candidate_count} library entries.
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
                {applySnapshotOperatorLabel ?? "Confirm apply"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {plexLiveOpen ? (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="pruner-plex-live-modal-title"
          data-testid="pruner-plex-live-modal"
        >
          <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-lg border border-red-900/40 bg-[var(--mm-card-bg)] p-4 shadow-xl">
            <h3 id="pruner-plex-live-modal-title" className="text-base font-semibold text-red-100">
              Plex live: {PRUNER_REMOVE_BROKEN_LIBRARY_ENTRIES_LABEL}
            </h3>
            <p className="mt-2 text-sm text-[var(--mm-text2)]">
              This queues a <strong>live</strong> Pruner job for <strong>this Plex server instance</strong> and the{" "}
              <strong>{props.scope === "tv" ? "TV" : "Movies"}</strong> tab only. There is <strong>no preview</strong>{" "}
              and <strong>no dry run</strong>. The worker rescans Plex at execution time (capped); nothing is frozen
              from a snapshot.
            </p>
            {plexLiveEligQuery.isLoading ? (
              <p className="mt-3 text-sm text-[var(--mm-text2)]">Refreshing eligibility…</p>
            ) : plexLiveEligQuery.isError ? (
              <p className="mt-3 text-sm text-red-600" role="alert">
                {(plexLiveEligQuery.error as Error).message}
              </p>
            ) : plexLiveEligQuery.data ? (
              <>
                <ul className="mt-3 list-inside list-disc space-y-1 text-sm text-[var(--mm-text)]">
                  <li>
                    Server: <strong>{plexLiveEligQuery.data.display_name}</strong> ({plexLiveEligQuery.data.provider})
                  </li>
                  <li>
                    Scope: <strong>{plexLiveEligQuery.data.media_scope === "tv" ? "TV" : "Movies"}</strong>
                  </li>
                  <li>
                    Max library entries this run may attempt:{" "}
                    <strong>{plexLiveEligQuery.data.live_max_items_cap}</strong>
                  </li>
                </ul>
                {!plexLiveEligQuery.data.eligible ? (
                  <p className="mt-3 text-sm text-amber-700" role="status">
                    {plexLiveEligQuery.data.reasons.join(" ")}
                  </p>
                ) : null}
                {plexLiveEligQuery.data.eligible ? (
                  <div className="mt-4 space-y-3 text-sm text-[var(--mm-text)]">
                    <label className="flex cursor-pointer items-start gap-2">
                      <input
                        type="checkbox"
                        className="mt-1"
                        data-testid="pruner-plex-live-ack-no-preview"
                        checked={plexNoPreviewAck}
                        onChange={(e) => setPlexNoPreviewAck(e.target.checked)}
                      />
                      <span>
                        I understand there is <strong>no preview</strong> and <strong>no dry run</strong> for Plex on
                        this screen, and the job runs <strong>live</strong> against the server.
                      </span>
                    </label>
                    <label className="flex cursor-pointer items-start gap-2">
                      <input
                        type="checkbox"
                        className="mt-1"
                        data-testid="pruner-plex-live-ack-live"
                        checked={plexLiveAck}
                        onChange={(e) => setPlexLiveAck(e.target.checked)}
                      />
                      <span>
                        I understand MediaMop may remove <strong>up to {plexLiveEligQuery.data.live_max_items_cap}</strong>{" "}
                        Plex library metadata rows for this instance and tab using Plex&apos;s live API, and that Plex
                        may or may not remove underlying media files depending on the Plex server.
                      </span>
                    </label>
                    <div>
                      <label className="block text-xs font-medium text-[var(--mm-text2)]" htmlFor="plex-live-phrase">
                        Type the confirmation phrase exactly (case-sensitive):
                      </label>
                      <input
                        id="plex-live-phrase"
                        type="text"
                        autoComplete="off"
                        className="mt-1 w-full rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-1.5 font-mono text-sm text-[var(--mm-text)]"
                        data-testid="pruner-plex-live-phrase"
                        value={plexTypedPhrase}
                        onChange={(e) => setPlexTypedPhrase(e.target.value)}
                        placeholder={plexLiveEligQuery.data.required_confirmation_phrase}
                      />
                      <p className="mt-1 text-xs text-[var(--mm-text2)]">
                        Required phrase:{" "}
                        <span className="font-mono text-[var(--mm-text)]">
                          {plexLiveEligQuery.data.required_confirmation_phrase}
                        </span>
                      </p>
                    </div>
                  </div>
                ) : null}
              </>
            ) : null}
            <div className="mt-4 flex flex-wrap justify-end gap-2">
              <button
                type="button"
                className="rounded-md border border-[var(--mm-border)] px-3 py-1.5 text-sm font-medium text-[var(--mm-text)]"
                onClick={() => closePlexLiveModal()}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded-md bg-red-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                data-testid="pruner-plex-live-confirm"
                disabled={
                  busy ||
                  !plexLiveEligQuery.data?.eligible ||
                  !plexNoPreviewAck ||
                  !plexLiveAck ||
                  plexTypedPhrase.trim() !== (plexLiveEligQuery.data?.required_confirmation_phrase ?? "") ||
                  plexLiveEligQuery.isLoading ||
                  plexLiveEligQuery.isError
                }
                onClick={() => void confirmPlexLiveRemoval()}
              >
                Queue Plex live job
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
