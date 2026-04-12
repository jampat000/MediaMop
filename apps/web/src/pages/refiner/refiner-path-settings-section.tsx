import { useEffect, useState } from "react";
import { PageLoading } from "../../components/shared/page-loading";
import { isHttpErrorFromApi, isLikelyNetworkFailure } from "../../lib/api/error-guards";
import { useMeQuery } from "../../lib/auth/queries";
import { useRefinerPathSettingsQuery, useRefinerPathSettingsSaveMutation } from "../../lib/refiner/queries";

function canEditRefinerPaths(role: string | undefined): boolean {
  return role === "operator" || role === "admin";
}

/** Refiner: persisted watched / work / output folders (SQLite singleton). */
export function RefinerPathSettingsSection() {
  const me = useMeQuery();
  const q = useRefinerPathSettingsQuery();
  const save = useRefinerPathSettingsSaveMutation();

  const [watched, setWatched] = useState("");
  const [work, setWork] = useState("");
  const [output, setOutput] = useState("");

  useEffect(() => {
    if (!q.data) {
      return;
    }
    setWatched(q.data.refiner_watched_folder ?? "");
    setWork(q.data.refiner_work_folder ?? "");
    setOutput(q.data.refiner_output_folder ?? "");
  }, [q.data]);

  const editable = canEditRefinerPaths(me.data?.role);

  const dirty =
    q.data !== undefined &&
    (watched !== (q.data.refiner_watched_folder ?? "") ||
      work !== (q.data.refiner_work_folder ?? "") ||
      output !== (q.data.refiner_output_folder ?? ""));

  if (q.isPending || me.isPending) {
    return <PageLoading label="Loading Refiner path settings" />;
  }
  if (q.isError) {
    return (
      <div
        className="mt-6 max-w-2xl rounded border border-red-900/40 bg-red-950/20 p-4 text-sm text-red-200"
        data-testid="refiner-path-settings-error"
        role="alert"
      >
        <p className="font-semibold">Could not load Refiner path settings</p>
        <p className="mt-1">
          {isLikelyNetworkFailure(q.error)
            ? "Check that the MediaMop API is running."
            : isHttpErrorFromApi(q.error)
              ? "Sign in, then try again."
              : "Request failed."}
        </p>
      </div>
    );
  }

  if (!q.data) {
    return null;
  }

  const d = q.data;

  return (
    <section
      className="mt-6 max-w-2xl rounded border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-4 text-sm leading-relaxed text-[var(--mm-text2)]"
      aria-labelledby="refiner-path-settings-heading"
      data-testid="refiner-path-settings"
    >
      <h2 id="refiner-path-settings-heading" className="text-base font-semibold text-[var(--mm-text)]">
        Refiner path settings
      </h2>
      <p className="mt-2">
        Watched, work/temp, and output folders are saved in the app database for Refiner only. Saving does{" "}
        <strong className="text-[var(--mm-text)]">not</strong> require a watched folder (it can stay blank). Manual{" "}
        <code className="rounded bg-black/25 px-1 py-0.5 font-mono text-[0.85em]">refiner.file.remux_pass.v1</code>{" "}
        jobs <strong className="text-[var(--mm-text)]">do</strong> require a watched folder before enqueue or worker
        run: it resolves <code className="font-mono text-[0.85em]">relative_media_path</code> and bounds automatic
        source cleanup. Watched, output, and work/temp must stay separate; overlapping paths are rejected on save. Live
        passes also need a saved output folder. Default work/temp lives under{" "}
        <code className="font-mono text-[0.85em]">MEDIAMOP_HOME</code> (shown below); leaving work blank on save stores
        that resolved path explicitly.
      </p>
      <p className="mt-2 text-[var(--mm-text3)]">
        Replacing an existing output file at the same relative path is allowed by default and is recorded on the
        Activity entry for each finished pass. After a successful live pass (including when remux was not required),
        the source file under the watched folder may be deleted automatically — not on dry run or failure.
      </p>

      {!editable ? (
        <p className="mt-3 text-xs text-[var(--mm-text3)]">Operators and admins can edit these paths.</p>
      ) : null}

      <div className="mt-4 space-y-3">
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">Watched folder</span>
          <input
            className="mt-1 w-full rounded border border-[var(--mm-border)] bg-[var(--mm-input-bg)] px-2 py-1.5 font-mono text-xs text-[var(--mm-text)]"
            value={watched}
            disabled={!editable || save.isPending}
            onChange={(e) => setWatched(e.target.value)}
            placeholder="Optional on save; required before manual remux enqueue/run"
          />
        </label>
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">Work / temp folder</span>
          <input
            className="mt-1 w-full rounded border border-[var(--mm-border)] bg-[var(--mm-input-bg)] px-2 py-1.5 font-mono text-xs text-[var(--mm-text)]"
            value={work}
            disabled={!editable || save.isPending}
            onChange={(e) => setWork(e.target.value)}
            placeholder={d.resolved_default_work_folder}
          />
          <span className="mt-1 block text-xs text-[var(--mm-text3)]">
            Effective work folder now: <span className="font-mono">{d.effective_work_folder}</span>
          </span>
        </label>
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
            Output folder <span className="text-red-300">(required)</span>
          </span>
          <input
            className="mt-1 w-full rounded border border-[var(--mm-border)] bg-[var(--mm-input-bg)] px-2 py-1.5 font-mono text-xs text-[var(--mm-text)]"
            value={output}
            disabled={!editable || save.isPending}
            onChange={(e) => setOutput(e.target.value)}
            placeholder="Existing directory; relative layout under watched is preserved"
            required
          />
        </label>
      </div>

      {save.isError ? (
        <p className="mt-3 text-sm text-red-300" role="alert" data-testid="refiner-path-settings-save-error">
          {save.error instanceof Error ? save.error.message : "Save failed."}
        </p>
      ) : null}

      {save.isSuccess && !dirty ? (
        <p className="mt-3 text-xs text-[var(--mm-text3)]" data-testid="refiner-path-settings-saved-hint">
          Saved.
        </p>
      ) : null}

      <div className="mt-4">
        <button
          type="button"
          className="rounded bg-[var(--mm-accent)] px-3 py-1.5 text-sm font-medium text-[var(--mm-accent-contrast)] disabled:opacity-50"
          disabled={!editable || !dirty || save.isPending || !output.trim()}
          onClick={() =>
            save.mutate({
              refiner_watched_folder: watched.trim() ? watched.trim() : null,
              refiner_work_folder: work.trim() ? work.trim() : null,
              refiner_output_folder: output.trim(),
            })
          }
        >
          {save.isPending ? "Saving…" : "Save path settings"}
        </button>
      </div>
    </section>
  );
}
