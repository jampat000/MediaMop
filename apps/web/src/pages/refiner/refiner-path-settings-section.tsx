import { useEffect, useState } from "react";
import { PageLoading } from "../../components/shared/page-loading";
import { isHttpErrorFromApi, isLikelyNetworkFailure } from "../../lib/api/error-guards";
import { useMeQuery } from "../../lib/auth/queries";
import { useRefinerPathSettingsQuery, useRefinerPathSettingsSaveMutation } from "../../lib/refiner/queries";
import { mmActionButtonClass, mmEditableTextFieldClass, mmTechnicalMonoSmallClass } from "../../lib/ui/mm-control-roles";

function canEditRefinerPaths(role: string | undefined): boolean {
  return role === "operator" || role === "admin";
}

/** Refiner: persisted Movies and TV watched / work / output (one module; independent path triplets). */
export function RefinerPathSettingsSection() {
  const me = useMeQuery();
  const q = useRefinerPathSettingsQuery();
  const save = useRefinerPathSettingsSaveMutation();

  const [watched, setWatched] = useState("");
  const [work, setWork] = useState("");
  const [output, setOutput] = useState("");
  const [tvWatched, setTvWatched] = useState("");
  const [tvWork, setTvWork] = useState("");
  const [tvOutput, setTvOutput] = useState("");

  useEffect(() => {
    if (!q.data) {
      return;
    }
    setWatched(q.data.refiner_watched_folder ?? "");
    setWork(q.data.refiner_work_folder ?? "");
    setOutput(q.data.refiner_output_folder ?? "");
    setTvWatched(q.data.refiner_tv_watched_folder ?? "");
    setTvWork(q.data.refiner_tv_work_folder ?? "");
    setTvOutput(q.data.refiner_tv_output_folder ?? "");
  }, [q.data]);

  const editable = canEditRefinerPaths(me.data?.role);

  const moviesDirty =
    q.data !== undefined &&
    (watched !== (q.data.refiner_watched_folder ?? "") ||
      work !== (q.data.refiner_work_folder ?? "") ||
      output !== (q.data.refiner_output_folder ?? ""));
  const tvDirty =
    q.data !== undefined &&
    (tvWatched !== (q.data.refiner_tv_watched_folder ?? "") ||
      tvWork !== (q.data.refiner_tv_work_folder ?? "") ||
      tvOutput !== (q.data.refiner_tv_output_folder ?? ""));
  const tvNeedsOutput = tvWatched.trim().length > 0;
  const tvOutputMissing = tvNeedsOutput && tvOutput.trim().length === 0;

  if (q.isPending || me.isPending) {
    return <PageLoading label="Loading Refiner path settings" />;
  }
  if (q.isError) {
    return (
      <div
        className="mm-fetcher-module-surface w-full min-w-0 rounded border border-red-900/40 bg-red-950/20 p-4 text-sm text-red-200"
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
      className="mm-fetcher-module-surface w-full min-w-0 rounded border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-5 text-sm leading-relaxed text-[var(--mm-text2)] sm:p-6"
      aria-labelledby="refiner-path-settings-heading"
      data-testid="refiner-path-settings"
    >
      <h2 id="refiner-path-settings-heading" className="text-base font-semibold text-[var(--mm-text)]">
        Saved folders
      </h2>
      <p className="mt-2">
        <strong className="text-[var(--mm-text)]">Movies</strong> and{" "}
        <strong className="text-[var(--mm-text)]">TV</strong> each get their own watched, work, and output roots. Pick
        the scope when you queue work—paths never cross between the two.
      </p>
      <p className="mt-2 text-xs text-[var(--mm-text3)]">
        Save rules: Movies output is always required. TV output is required whenever TV watched is set. Movies and TV
        paths cannot overlap.
      </p>
      <p className="mt-3 rounded-md border border-[var(--mm-border)]/80 bg-[var(--mm-accent-soft)]/10 px-3 py-2 text-xs text-[var(--mm-text3)]">
        After a successful <strong className="text-[var(--mm-text)]">live</strong> file pass, MediaMop may delete only
        the watched-folder <strong className="text-[var(--mm-text)]">source media file</strong> that was remuxed. Dry
        runs and failures never delete sources. Refiner does not sweep sidecars or remove empty folders.
      </p>

      {!editable ? (
        <p className="mt-3 text-xs text-[var(--mm-text3)]">Operators and admins can edit these paths.</p>
      ) : null}

      <div className="mt-6 grid gap-5 lg:grid-cols-2">
        <div className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)]/60 p-4">
          <h3 className="text-sm font-semibold text-[var(--mm-text1)]">TV library</h3>
          <p className="mt-1 text-xs text-[var(--mm-text3)]">
            Default work when blank: <span className={mmTechnicalMonoSmallClass}>{d.resolved_default_tv_work_folder}</span>
          </p>
          <div className="mt-3 space-y-3">
            <label className="block">
              <span className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">Watched folder</span>
              <input
                className={mmEditableTextFieldClass}
                value={tvWatched}
                disabled={!editable || save.isPending}
                onChange={(e) => setTvWatched(e.target.value)}
                placeholder=""
              />
            </label>
            <label className="block">
              <span className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">Work / temp folder</span>
              <input
                className={mmEditableTextFieldClass}
                value={tvWork}
                disabled={!editable || save.isPending}
                onChange={(e) => setTvWork(e.target.value)}
                placeholder={d.resolved_default_tv_work_folder}
              />
              <span className="mt-1 block text-xs text-[var(--mm-text3)]">
                Effective work folder now: <span className={mmTechnicalMonoSmallClass}>{d.effective_tv_work_folder}</span>
              </span>
            </label>
            <label className="block">
              <span className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
                Output folder
              </span>
              <input
                className={mmEditableTextFieldClass}
                value={tvOutput}
                disabled={!editable || save.isPending}
                onChange={(e) => setTvOutput(e.target.value)}
                placeholder=""
              />
            </label>
            {tvOutputMissing ? (
              <p className="text-xs text-amber-200/90">
                Add a TV output folder before saving while TV watched folder is set.
              </p>
            ) : null}
            <div className="pt-2">
              <button
                type="button"
                className={mmActionButtonClass({
                  variant: "primary",
                  disabled: !editable || !tvDirty || save.isPending || tvOutputMissing,
                })}
                disabled={!editable || !tvDirty || save.isPending || tvOutputMissing}
                onClick={() =>
                  save.mutate({
                    refiner_watched_folder: (q.data?.refiner_watched_folder ?? "").trim()
                      ? (q.data?.refiner_watched_folder ?? "").trim()
                      : null,
                    refiner_work_folder: (q.data?.refiner_work_folder ?? "").trim()
                      ? (q.data?.refiner_work_folder ?? "").trim()
                      : null,
                    refiner_output_folder: (q.data?.refiner_output_folder ?? "").trim(),
                    refiner_tv_paths_included: true,
                    refiner_tv_watched_folder: tvWatched.trim() ? tvWatched.trim() : null,
                    refiner_tv_work_folder: tvWork.trim() ? tvWork.trim() : null,
                    refiner_tv_output_folder: tvOutput.trim() ? tvOutput.trim() : null,
                  })
                }
              >
                {save.isPending ? "Saving…" : "Save TV path settings"}
              </button>
            </div>
          </div>
        </div>

        <div className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)]/60 p-4">
          <h3 className="text-sm font-semibold text-[var(--mm-text1)]">Movies library</h3>
          <p className="mt-1 text-xs text-[var(--mm-text3)]">
            Default work when blank: <span className={mmTechnicalMonoSmallClass}>{d.resolved_default_work_folder}</span>
          </p>
          <div className="mt-3 space-y-3">
            <label className="block">
              <span className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">Watched folder</span>
              <input
                className={mmEditableTextFieldClass}
                value={watched}
                disabled={!editable || save.isPending}
                onChange={(e) => setWatched(e.target.value)}
                placeholder=""
              />
            </label>
            <label className="block">
              <span className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">Work / temp folder</span>
              <input
                className={mmEditableTextFieldClass}
                value={work}
                disabled={!editable || save.isPending}
                onChange={(e) => setWork(e.target.value)}
                placeholder={d.resolved_default_work_folder}
              />
              <span className="mt-1 block text-xs text-[var(--mm-text3)]">
                Effective work folder now: <span className={mmTechnicalMonoSmallClass}>{d.effective_work_folder}</span>
              </span>
            </label>
            <label className="block">
              <span className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
                Output folder
              </span>
              <input
                className={mmEditableTextFieldClass}
                value={output}
                disabled={!editable || save.isPending}
                onChange={(e) => setOutput(e.target.value)}
                placeholder=""
                required
              />
            </label>
            <div className="pt-2">
              <button
                type="button"
                className={mmActionButtonClass({
                  variant: "primary",
                  disabled: !editable || !moviesDirty || save.isPending || !output.trim(),
                })}
                disabled={!editable || !moviesDirty || save.isPending || !output.trim()}
                onClick={() =>
                  save.mutate({
                    refiner_watched_folder: watched.trim() ? watched.trim() : null,
                    refiner_work_folder: work.trim() ? work.trim() : null,
                    refiner_output_folder: output.trim(),
                    refiner_tv_paths_included: true,
                    refiner_tv_watched_folder: (q.data?.refiner_tv_watched_folder ?? "").trim()
                      ? (q.data?.refiner_tv_watched_folder ?? "").trim()
                      : null,
                    refiner_tv_work_folder: (q.data?.refiner_tv_work_folder ?? "").trim()
                      ? (q.data?.refiner_tv_work_folder ?? "").trim()
                      : null,
                    refiner_tv_output_folder: (q.data?.refiner_tv_output_folder ?? "").trim()
                      ? (q.data?.refiner_tv_output_folder ?? "").trim()
                      : null,
                  })
                }
              >
                {save.isPending ? "Saving…" : "Save Movies path settings"}
              </button>
            </div>
          </div>
        </div>
      </div>

      {save.isError ? (
        <p className="mt-3 text-sm text-red-300" role="alert" data-testid="refiner-path-settings-save-error">
          {save.error instanceof Error ? save.error.message : "Save failed."}
        </p>
      ) : null}

      {save.isSuccess && !moviesDirty && !tvDirty ? (
        <p className="mt-3 text-xs text-[var(--mm-text3)]" data-testid="refiner-path-settings-saved-hint">
          Saved.
        </p>
      ) : null}

    </section>
  );
}
