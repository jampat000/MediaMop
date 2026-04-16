import { useEffect, useId, useState } from "react";
import { MmListboxPicker, type MmListboxOption } from "../../components/ui/mm-listbox-picker";
import { PageLoading } from "../../components/shared/page-loading";
import { isHttpErrorFromApi, isLikelyNetworkFailure } from "../../lib/api/error-guards";
import { useMeQuery } from "../../lib/auth/queries";
import { useRefinerOperatorSettingsQuery, useRefinerOperatorSettingsSaveMutation } from "../../lib/refiner/queries";
import { mmActionButtonClass } from "../../lib/ui/mm-control-roles";

function canEdit(role: string | undefined): boolean {
  return role === "operator" || role === "admin";
}

const FILES_AT_ONCE_OPTIONS: MmListboxOption[] = Array.from({ length: 8 }, (_, i) => ({
  value: String(i + 1),
  label: String(i + 1),
}));

/** Throughput and file-age gates (not paths or poll intervals — those live under Libraries). */
export function RefinerProcessSettingsSection() {
  const me = useMeQuery();
  const q = useRefinerOperatorSettingsQuery();
  const save = useRefinerOperatorSettingsSaveMutation();
  const filesAtOnceLabelId = useId();
  const editable = canEdit(me.data?.role);

  const [maxConcurrentFiles, setMaxConcurrentFiles] = useState("1");
  const [minFileAgeSeconds, setMinFileAgeSeconds] = useState("60");

  useEffect(() => {
    if (!q.data) {
      return;
    }
    setMaxConcurrentFiles(String(q.data.max_concurrent_files));
    setMinFileAgeSeconds(String(q.data.min_file_age_seconds));
  }, [q.data]);

  if (q.isPending || me.isPending) {
    return <PageLoading label="Loading Refiner processing settings" />;
  }
  if (q.isError) {
    return (
      <div className="mm-fetcher-module-surface w-full min-w-0 rounded border border-red-900/40 bg-red-950/20 p-4 text-sm text-red-200" role="alert">
        <p className="font-semibold">Could not load Refiner processing settings</p>
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
  const draftValid =
    Number.isFinite(draftConcurrent) &&
    draftConcurrent >= 1 &&
    draftConcurrent <= 8 &&
    Number.isFinite(draftMinAge) &&
    draftMinAge >= 0;
  const dirty =
    maxConcurrentFiles !== String(q.data.max_concurrent_files) || minFileAgeSeconds !== String(q.data.min_file_age_seconds);

  return (
    <section className="mm-fetcher-module-surface w-full min-w-0 rounded border border-[var(--mm-border)] bg-[var(--mm-card-bg)] p-6 text-sm leading-relaxed text-[var(--mm-text2)] sm:p-7">
      <h2 className="text-base font-semibold text-[var(--mm-text)]">Processing settings</h2>
      <p className="mt-2 max-w-3xl text-[var(--mm-text3)]">
        Control how many files Refiner works on at once and how long a file must sit unchanged before processing. Timed
        scans and per-library folder checks are under <strong className="text-[var(--mm-text2)]">Schedules</strong> and{" "}
        <strong className="text-[var(--mm-text2)]">Libraries</strong>.
      </p>
      <div className="mt-6 grid gap-4 sm:grid-cols-2 sm:gap-5">
        <div className="block min-w-0">
          <span id={filesAtOnceLabelId} className="text-xs font-semibold uppercase tracking-wide text-[var(--mm-text3)]">
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
      </div>
      {save.isError ? (
        <p className="mt-3 text-sm text-red-300" role="alert">
          {save.error instanceof Error ? save.error.message : "Save failed."}
        </p>
      ) : null}
      <div className="mt-8 border-t border-[var(--mm-border)] pt-5">
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
            })
          }
        >
          {save.isPending ? "Saving…" : "Save processing settings"}
        </button>
      </div>
    </section>
  );
}
