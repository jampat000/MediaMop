import { useEffect, useId, useState } from "react";
import {
  MmListboxPicker,
  type MmListboxOption,
} from "../../components/ui/mm-listbox-picker";
import { PageLoading } from "../../components/shared/page-loading";
import {
  isHttpErrorFromApi,
  isLikelyNetworkFailure,
} from "../../lib/api/error-guards";
import { useMeQuery } from "../../lib/auth/queries";
import {
  useRefinerOperatorSettingsQuery,
  useRefinerOperatorSettingsSaveMutation,
} from "../../lib/refiner/queries";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";

function canEdit(role: string | undefined): boolean {
  return role === "operator" || role === "admin";
}

const FILES_AT_ONCE_OPTIONS: MmListboxOption[] = Array.from(
  { length: 8 },
  (_, i) => ({
    value: String(i + 1),
    label: String(i + 1),
  }),
);

/** Throughput and file-age gates (not paths or poll intervals — those live under Libraries). */
export function RefinerProcessSettingsSection() {
  const me = useMeQuery();
  const q = useRefinerOperatorSettingsQuery();
  const save = useRefinerOperatorSettingsSaveMutation();
  const filesAtOnceLabelId = useId();
  const editable = canEdit(me.data?.role);

  const [maxConcurrentFiles, setMaxConcurrentFiles] = useState("1");
  const [minFileAgeSeconds, setMinFileAgeSeconds] = useState("60");
  const [minInputFileSizeMb, setMinInputFileSizeMb] = useState("50");
  const [minimumFreeDiskSpaceGb, setMinimumFreeDiskSpaceGb] = useState("5");

  useEffect(() => {
    if (!q.data) {
      return;
    }
    setMaxConcurrentFiles(String(q.data.max_concurrent_files));
    setMinFileAgeSeconds(String(q.data.min_file_age_seconds));
    setMinInputFileSizeMb(String(q.data.refiner_min_input_file_size_mb));
    setMinimumFreeDiskSpaceGb(
      String(Math.max(0, q.data.minimum_free_disk_space_mb / 1024)),
    );
  }, [q.data]);

  if (q.isPending || me.isPending) {
    return <PageLoading label="Loading Refiner processing settings" />;
  }
  if (q.isError) {
    return (
      <div
        className="mm-module-surface w-full min-w-0 rounded border border-red-900/40 bg-red-950/20 p-4 text-sm text-red-200"
        role="alert"
      >
        <p className="font-semibold">
          Could not load Refiner processing settings
        </p>
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

  const draftConcurrent = Number.parseInt(maxConcurrentFiles, 10);
  const draftMinAge = Number.parseInt(minFileAgeSeconds, 10);
  const draftMinInputSize = Number.parseInt(minInputFileSizeMb, 10);
  const draftMinimumFreeGb = Number.parseFloat(minimumFreeDiskSpaceGb);
  const draftMinimumFreeMb = Math.round(draftMinimumFreeGb * 1024);
  const draftValid =
    Number.isFinite(draftConcurrent) &&
    draftConcurrent >= 1 &&
    draftConcurrent <= 8 &&
    Number.isFinite(draftMinAge) &&
    draftMinAge >= 0 &&
    Number.isFinite(draftMinInputSize) &&
    draftMinInputSize >= 0 &&
    Number.isFinite(draftMinimumFreeGb) &&
    draftMinimumFreeGb >= 0;
  const dirty =
    maxConcurrentFiles !== String(q.data.max_concurrent_files) ||
    minFileAgeSeconds !== String(q.data.min_file_age_seconds) ||
    minInputFileSizeMb !== String(q.data.refiner_min_input_file_size_mb) ||
    draftMinimumFreeMb !== q.data.minimum_free_disk_space_mb;

  return (
    <section className="mm-module-surface flex w-full min-w-0 flex-col rounded border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-6 text-sm leading-relaxed text-[var(--mm-text2)] sm:p-7">
      <h2 className="text-base font-semibold text-[var(--mm-text)]">
        Processing settings
      </h2>
      <p className="mt-2 max-w-3xl text-[var(--mm-text3)]">
        Control how many files Refiner works on at once and how long a file must
        sit unchanged before processing. Per-library watched-folder timers are
        under <strong className="text-[var(--mm-text2)]">Libraries</strong>.
      </p>
      <p className="mt-2 max-w-3xl text-[var(--mm-text3)]">
        Download-client disk limits are still recommended. MediaMop adds this
        final safety check before Refiner or Subber writes to a target drive.
      </p>
      <div className="mm-card-action-body mt-6 flex-1 min-h-0">
        <div className="grid gap-4 sm:grid-cols-2 sm:gap-5">
          <div className="block min-w-0">
            <span
              id={filesAtOnceLabelId}
              className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]"
            >
              Files at once
            </span>
            <MmListboxPicker
              className="w-full min-w-0"
              options={FILES_AT_ONCE_OPTIONS}
              value={maxConcurrentFiles}
              disabled={!editable || save.isPending}
              onChange={setMaxConcurrentFiles}
              ariaLabelledBy={filesAtOnceLabelId}
              placeholder="Select…"
            />
          </div>
          <label className="block">
            <span className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
              Minimum file age before processing (seconds)
            </span>
            <input
              type="number"
              min={0}
              value={minFileAgeSeconds}
              disabled={!editable || save.isPending}
              onChange={(e) => setMinFileAgeSeconds(e.target.value)}
              className="mm-input mt-1 w-full"
            />
          </label>
          <label className="block">
            <span className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
              Minimum file size (MB) — files smaller than this will be skipped
            </span>
            <input
              type="number"
              min={0}
              value={minInputFileSizeMb}
              disabled={!editable || save.isPending}
              onChange={(e) => setMinInputFileSizeMb(e.target.value)}
              className="mm-input mt-1 w-full"
            />
          </label>
          <label className="block">
            <span className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
              Minimum free disk space (GB) — processing will not start below
              this threshold
            </span>
            <input
              type="number"
              min={0}
              step={0.1}
              value={minimumFreeDiskSpaceGb}
              disabled={!editable || save.isPending}
              onChange={(e) => setMinimumFreeDiskSpaceGb(e.target.value)}
              className="mm-input mt-1 w-full"
            />
          </label>
        </div>
        {save.isError ? (
          <p className="mt-3 text-sm text-red-300" role="alert">
            {save.error instanceof Error ? save.error.message : "Save failed."}
          </p>
        ) : null}
      </div>
      <div className="mm-card-action-footer">
        <button
          type="button"
          className={mmActionButtonClass({
            variant: "primary",
            disabled: !editable || !dirty || !draftValid || save.isPending,
          })}
          disabled={!editable || !dirty || !draftValid || save.isPending}
          onClick={() =>
            save.mutate({
              max_concurrent_files: draftConcurrent,
              min_file_age_seconds: draftMinAge,
              refiner_min_input_file_size_mb: draftMinInputSize,
              minimum_free_disk_space_mb: draftMinimumFreeMb,
            })
          }
        >
          {save.isPending ? "Saving…" : "Save processing settings"}
        </button>
      </div>
    </section>
  );
}
