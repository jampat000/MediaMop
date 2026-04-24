import { useEffect, useId, useState } from "react";
import { PageLoading } from "../../components/shared/page-loading";
import { isHttpErrorFromApi, isLikelyNetworkFailure } from "../../lib/api/error-guards";
import { MmListboxPicker, type MmListboxOption } from "../../components/ui/mm-listbox-picker";
import { ServerFolderPickerButton } from "../../components/ui/server-folder-picker-button";
import { useMeQuery } from "../../lib/auth/queries";
import { useRefinerPathSettingsQuery, useRefinerPathSettingsSaveMutation } from "../../lib/refiner/queries";
import { mmActionButtonClass, mmEditableTextFieldClass, mmTechnicalMonoSmallClass } from "../../lib/ui/mm-control-roles";

const WATCHED_FOLDER_INTERVAL_OPTIONS: MmListboxOption[] = Array.from({ length: 30 }, (_, i) => {
  const seconds = 10 + i * 10;
  return { value: String(seconds), label: `${seconds} seconds` };
});

function canEditRefinerPaths(role: string | undefined): boolean {
  return role === "operator" || role === "admin";
}

/** Refiner: persisted TV and Movies watched / work / output (one module; independent path triplets). */
export function RefinerPathSettingsSection() {
  const me = useMeQuery();
  const q = useRefinerPathSettingsQuery();
  const save = useRefinerPathSettingsSaveMutation();
  const tvIntervalLabelId = useId();
  const movieIntervalLabelId = useId();

  const [watched, setWatched] = useState("");
  const [work, setWork] = useState("");
  const [output, setOutput] = useState("");
  const [tvWatched, setTvWatched] = useState("");
  const [tvWork, setTvWork] = useState("");
  const [tvOutput, setTvOutput] = useState("");
  const [movieWatchedFolderInterval, setMovieWatchedFolderInterval] = useState("300");
  const [tvWatchedFolderInterval, setTvWatchedFolderInterval] = useState("300");

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
    setMovieWatchedFolderInterval(String(q.data.movie_watched_folder_check_interval_seconds));
    setTvWatchedFolderInterval(String(q.data.tv_watched_folder_check_interval_seconds));
  }, [q.data]);

  const editable = canEditRefinerPaths(me.data?.role);

  const moviesDirty =
    q.data !== undefined &&
    (watched !== (q.data.refiner_watched_folder ?? "") ||
      work !== (q.data.refiner_work_folder ?? "") ||
      output !== (q.data.refiner_output_folder ?? "") ||
      movieWatchedFolderInterval !== String(q.data.movie_watched_folder_check_interval_seconds));
  const tvDirty =
    q.data !== undefined &&
    (tvWatched !== (q.data.refiner_tv_watched_folder ?? "") ||
      tvWork !== (q.data.refiner_tv_work_folder ?? "") ||
      tvOutput !== (q.data.refiner_tv_output_folder ?? "") ||
      tvWatchedFolderInterval !== String(q.data.tv_watched_folder_check_interval_seconds));
  const tvNeedsOutput = tvWatched.trim().length > 0;
  const tvOutputMissing = tvNeedsOutput && tvOutput.trim().length === 0;
  const movieNeedsOutput = watched.trim().length > 0;
  const movieOutputMissing = movieNeedsOutput && output.trim().length === 0;

  if (q.isPending || me.isPending) {
    return <PageLoading label="Loading Refiner path settings" />;
  }
  if (q.isError) {
    return (
      <div
        className="mm-module-surface w-full min-w-0 rounded border border-red-900/40 bg-red-950/20 p-4 text-sm text-red-200"
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
  const effectiveMovieWorkPreview = work.trim() ? work.trim() : d.effective_work_folder;
  const effectiveTvWorkPreview = tvWork.trim() ? tvWork.trim() : d.effective_tv_work_folder;

  function renderFolderInput({
    label,
    value,
    setter,
    title,
    required,
  }: {
    label: string;
    value: string;
    setter: (value: string) => void;
    title: string;
    required?: boolean;
  }) {
    return (
      <label className="block">
        <span className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">{label}</span>
        <div className="mt-1 flex flex-col gap-2 sm:flex-row">
          <input
            className={mmEditableTextFieldClass}
            value={value}
            disabled={!editable || save.isPending}
            onChange={(e) => setter(e.target.value)}
            placeholder=""
            required={required}
          />
          <ServerFolderPickerButton title={title} value={value} disabled={!editable || save.isPending} onSelect={setter} />
        </div>
      </label>
    );
  }

  return (
    <div className="mm-bubble-stack w-full min-w-0" data-testid="refiner-path-settings">
      <section
        className="mm-card mm-dash-card mm-module-surface w-full min-w-0 p-6 text-sm leading-relaxed text-[var(--mm-text2)] sm:p-7"
        aria-labelledby="refiner-path-settings-heading"
      >
      <h2 id="refiner-path-settings-heading" className="text-base font-semibold text-[var(--mm-text)]">
        Saved folders
      </h2>
      <p className="mt-2 max-w-3xl text-[var(--mm-text3)]">
        TV and Movies each use their own watched, work, and output folders. Paths do not cross between the two libraries.
      </p>
      <p className="mt-1 max-w-3xl text-xs text-[var(--mm-text3)]">
        TV needs a saved output folder whenever a TV watched folder is set. The Movies library needs a saved output folder.
        TV and Movies folder trees must not overlap.
      </p>

      <details className="group mt-5 rounded-md border border-[var(--mm-border)] bg-black/10 px-4 py-3 text-xs text-[var(--mm-text3)]">
        <summary className="cursor-pointer list-none font-medium text-[var(--mm-text2)] marker:hidden [&::-webkit-details-marker]:hidden">
          <span className="underline-offset-2 group-open:underline">What happens to your files</span>
        </summary>
        <p className="mt-3 border-t border-[var(--mm-border)] pt-3">
          Applies to per-file passes from the saved watched folder for{" "}
          <strong className="text-[var(--mm-text2)]">TV</strong> or{" "}
          <strong className="text-[var(--mm-text2)]">Movies</strong> (including when a folder scan queues that work). Other
          Refiner jobs follow different rules.
        </p>
        <div className="mt-3 space-y-2.5">
          <p>
            <span className="font-semibold text-[var(--mm-text2)]">Watched folder.</span> Refiner walks it recursively. It
            only treats{" "}
            <span className={mmTechnicalMonoSmallClass}>.mkv</span>, <span className={mmTechnicalMonoSmallClass}>.mp4</span>,{" "}
            <span className={mmTechnicalMonoSmallClass}>.m4v</span>, <span className={mmTechnicalMonoSmallClass}>.webm</span>, and{" "}
            <span className={mmTechnicalMonoSmallClass}>.avi</span> as media. Subtitles, <span className={mmTechnicalMonoSmallClass}>.nfo</span>,{" "}
            <span className={mmTechnicalMonoSmallClass}>.par2</span>, and other files are not treated as media candidates
            for this step. Whole-folder cleanup rules below can still remove them when a season or release folder is
            removed.
          </p>
          <p>
            <span className="font-semibold text-[var(--mm-text2)]">Work / temp.</span> When Refiner runs ffmpeg, it writes
            a temp file here, checks it, then moves it into your output folder. The default work folder is created if it
            is missing; a custom work folder must already exist. If ffmpeg or the check right after fails, Refiner
            removes that temp file when it can. Separately, Refiner can also run periodic cleanup of its own stale temp
            files under each scope&apos;s work folder — that is different from this one-file flow; schedule timers and
            manual scan controls are under <strong className="text-[var(--mm-text2)]">Schedules</strong>. If the move into
            output fails later, a temp file can be left behind.
          </p>
          <p>
            <span className="font-semibold text-[var(--mm-text2)]">Output.</span> Finished files use the same folder
            layout under output as under the watched folder. If something is already there, Refiner deletes it, then
            moves the new file in. If the move fails after that delete, you can lose the old file there without the new
            one in place. Refiner does not keep older copies or sweep stale outputs.
          </p>
          <p>
            <span className="font-semibold text-[var(--mm-text2)]">Output library cleanup.</span> After a successful{" "}
            remux, Refiner may optionally remove the whole output
            folder that held the file — per title for Movies, per season for TV — only when library checks and other safety
            gates pass.
          </p>
          <p>
            <span className="font-semibold text-[var(--mm-text2)]">TV after a successful live pass.</span> When every
            episode media file directly in the same season folder passes Refiner's safety checks (including Sonarr
            queue status, whether another TV remux job is already running, finished output checks for files Refiner already
            processed, and minimum file age for files Refiner never touched), Refiner may remove the whole season folder
            under your TV watched folder — that removes episodes, subtitles, artwork, and subfolders together. If any
            check fails, nothing in that season folder is removed. Refiner never removes your TV watched folder itself.
          </p>
          <p>
            <span className="font-semibold text-[var(--mm-text2)]">Movies after a successful live pass.</span> Refiner may
            remove the entire movie release folder under your Movies watched folder — the folder that holds the file that
            was processed — but only when the output file at the expected path was found and verified. If output cannot be
            verified, folder removal is skipped (including when no remux was needed and there is no output file at that path
            yet). This whole-folder step is Movies-only.
          </p>
          <p>
            <span className="font-semibold text-[var(--mm-text2)]">If a pass fails.</span> Refiner does not delete the
            source. Output is usually unchanged, unless an existing destination was already removed and the move then
            failed. Temp files are removed when ffmpeg or the post-ffmpeg check fails; that is not true for every failure
            that happens after that. Separately from this one-file flow, Refiner can run periodic failed-job cleanup for
            terminal failed remux jobs after a per-scope grace period. That later sweep may remove failed source/output
            leftovers and matching Refiner temp files only when safety gates pass. If Radarr/Sonarr is unavailable or still
            shows the file/season in queue, Refiner skips cleanup.
          </p>
        </div>
      </details>

      {!editable ? (
        <p className="mt-4 text-xs text-[var(--mm-text3)]">Operators and admins can edit these paths.</p>
      ) : null}
      </section>

      <div className="mm-dash-grid">
        <div className="mm-card mm-dash-card flex flex-col p-5 sm:p-6">
          <div className="border-b border-[var(--mm-border)] pb-4">
            <p className="text-[0.7rem] font-semibold uppercase tracking-[0.16em] text-[var(--mm-text3)]">Library</p>
            <h3 className="mt-1 text-sm font-semibold text-[var(--mm-text1)]">TV</h3>
          </div>
          <p className="mt-4 text-xs leading-relaxed text-[var(--mm-text3)]">
            If work is blank, Refiner uses: <span className={mmTechnicalMonoSmallClass}>{d.resolved_default_tv_work_folder}</span>
          </p>
          <div className="mt-6 flex min-h-0 flex-1 flex-col">
            <div className="mm-card-action-body flex-1 min-h-0">
            <div>
              {renderFolderInput({
                label: "Watched folder",
                value: tvWatched,
                setter: setTvWatched,
                title: "Choose TV watched folder",
              })}
              {tvWatched.trim() && !d.refiner_tv_watched_folder_exists ? (
                <span className="mt-1 block text-xs text-amber-200/90">
                  This folder is not on disk yet. Save is allowed. Refiner will warn at runtime until it exists.
                </span>
              ) : null}
            </div>
            <div>
              {renderFolderInput({
                label: "Work / temp folder",
                value: tvWork,
                setter: setTvWork,
                title: "Choose TV work folder",
              })}
              <span className="mt-1 block text-xs text-[var(--mm-text3)]">
                Effective work folder now: <span className={mmTechnicalMonoSmallClass}>{effectiveTvWorkPreview}</span>
              </span>
            </div>
            {renderFolderInput({
              label: "Output folder",
              value: tvOutput,
              setter: setTvOutput,
              title: "Choose TV output folder",
            })}
            <div className="border-t border-[var(--mm-border)] pt-6 pb-6">
              <span id={tvIntervalLabelId} className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
                Watched folder interval
              </span>
              <p className="mt-1 text-xs leading-relaxed text-[var(--mm-text3)]">
                How often this library is checked for periodic TV scans. Independent of Movies.
              </p>
              <MmListboxPicker
                className="mt-2 max-w-md"
                options={WATCHED_FOLDER_INTERVAL_OPTIONS}
                value={tvWatchedFolderInterval}
                disabled={!editable || save.isPending}
                onChange={setTvWatchedFolderInterval}
                ariaLabelledBy={tvIntervalLabelId}
                placeholder="Select interval"
              />
            </div>
            {tvOutputMissing ? (
              <p className="text-xs text-amber-200/90">
                Set a TV output folder before saving when TV watched is set.
              </p>
            ) : null}
            </div>
            <div className="mm-card-action-footer">
              <button
                type="button"
                className={mmActionButtonClass({
                  variant: "primary",
                  disabled: !editable || !tvDirty || save.isPending || tvOutputMissing,
                })}
                disabled={!editable || !tvDirty || save.isPending || tvOutputMissing}
                onClick={() =>
                  save.mutate({
                    refiner_watched_folder: watched.trim() ? watched.trim() : null,
                    refiner_work_folder: work.trim() ? work.trim() : null,
                    refiner_output_folder: output.trim() ? output.trim() : null,
                    refiner_tv_paths_included: true,
                    refiner_tv_watched_folder: tvWatched.trim() ? tvWatched.trim() : null,
                    refiner_tv_work_folder: tvWork.trim() ? tvWork.trim() : null,
                    refiner_tv_output_folder: tvOutput.trim() ? tvOutput.trim() : null,
                    movie_watched_folder_check_interval_seconds: Number.parseInt(movieWatchedFolderInterval, 10),
                    tv_watched_folder_check_interval_seconds: Number.parseInt(tvWatchedFolderInterval, 10),
                  })
                }
              >
                {save.isPending ? "Saving..." : "Save TV path settings"}
              </button>
            </div>
          </div>
        </div>

        <div className="mm-card mm-dash-card flex flex-col p-5 sm:p-6">
          <div className="border-b border-[var(--mm-border)] pb-4">
            <p className="text-[0.7rem] font-semibold uppercase tracking-[0.16em] text-[var(--mm-text3)]">Library</p>
            <h3 className="mt-1 text-sm font-semibold text-[var(--mm-text1)]">Movies</h3>
          </div>
          <p className="mt-4 text-xs leading-relaxed text-[var(--mm-text3)]">
            If work is blank, Refiner uses: <span className={mmTechnicalMonoSmallClass}>{d.resolved_default_work_folder}</span>
          </p>
          <div className="mt-6 flex min-h-0 flex-1 flex-col">
            <div className="mm-card-action-body flex-1 min-h-0">
            <div>
              {renderFolderInput({
                label: "Watched folder",
                value: watched,
                setter: setWatched,
                title: "Choose Movies watched folder",
              })}
              {watched.trim() && !d.refiner_watched_folder_exists ? (
                <span className="mt-1 block text-xs text-amber-200/90">
                  This folder is not on disk yet. Save is allowed. Refiner will warn at runtime until it exists.
                </span>
              ) : null}
            </div>
            <div>
              {renderFolderInput({
                label: "Work / temp folder",
                value: work,
                setter: setWork,
                title: "Choose Movies work folder",
              })}
              <span className="mt-1 block text-xs text-[var(--mm-text3)]">
                Effective work folder now: <span className={mmTechnicalMonoSmallClass}>{effectiveMovieWorkPreview}</span>
              </span>
            </div>
            {renderFolderInput({
              label: "Output folder",
              value: output,
              setter: setOutput,
              title: "Choose Movies output folder",
              required: true,
            })}
            <div className="border-t border-[var(--mm-border)] pt-6 pb-6">
              <span id={movieIntervalLabelId} className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
                Watched folder interval
              </span>
              <p className="mt-1 text-xs leading-relaxed text-[var(--mm-text3)]">
                How often this library is checked for periodic Movies scans. Independent of TV.
              </p>
              <MmListboxPicker
                className="mt-2 max-w-md"
                options={WATCHED_FOLDER_INTERVAL_OPTIONS}
                value={movieWatchedFolderInterval}
                disabled={!editable || save.isPending}
                onChange={setMovieWatchedFolderInterval}
                ariaLabelledBy={movieIntervalLabelId}
                placeholder="Select interval"
              />
            </div>
            </div>
            {movieOutputMissing ? (
              <p className="text-xs text-amber-200/90">
                Set a Movies output folder before saving when Movies watched is set.
              </p>
            ) : null}
            <div className="mm-card-action-footer">
              <button
                type="button"
                className={mmActionButtonClass({
                  variant: "primary",
                  disabled: !editable || !moviesDirty || save.isPending || movieOutputMissing,
                })}
                disabled={!editable || !moviesDirty || save.isPending || movieOutputMissing}
                onClick={() =>
                  save.mutate({
                    refiner_watched_folder: watched.trim() ? watched.trim() : null,
                    refiner_work_folder: work.trim() ? work.trim() : null,
                    refiner_output_folder: output.trim() ? output.trim() : null,
                    refiner_tv_paths_included: true,
                    refiner_tv_watched_folder: tvWatched.trim() ? tvWatched.trim() : null,
                    refiner_tv_work_folder: tvWork.trim() ? tvWork.trim() : null,
                    refiner_tv_output_folder: tvOutput.trim() ? tvOutput.trim() : null,
                    movie_watched_folder_check_interval_seconds: Number.parseInt(movieWatchedFolderInterval, 10),
                    tv_watched_folder_check_interval_seconds: Number.parseInt(tvWatchedFolderInterval, 10),
                  })
                }
              >
                {save.isPending ? "Saving..." : "Save Movies path settings"}
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

    </div>
  );
}
