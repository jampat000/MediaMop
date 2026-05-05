type PrunerScopeTabDefaultIntroProps = {
  scope: "tv" | "movies";
  label: string;
  libraryTabPhrase: string;
  disabledMode?: boolean;
  showInteractiveControls: boolean;
  busy: boolean;
  isPlex: boolean;
  previewMaxItems: number;
  setPreviewMaxItems: (value: number) => void;
  previewMaxItemsMsg: string | null;
  scopePreviewMaxItems: number | undefined;
  savePreviewMaxItemsSettings: () => Promise<void>;
};

export function PrunerScopeTabDefaultIntro({
  scope,
  label,
  libraryTabPhrase,
  disabledMode,
  showInteractiveControls,
  busy,
  isPlex,
  previewMaxItems,
  setPreviewMaxItems,
  previewMaxItemsMsg,
  scopePreviewMaxItems,
  savePreviewMaxItemsSettings,
}: PrunerScopeTabDefaultIntroProps) {
  return (
    <>
      <h2
        id="pruner-scope-heading"
        className="text-base font-semibold text-[var(--mm-text)]"
      >
        {label}
      </h2>
      {disabledMode ? (
        <p className="rounded-md border border-dashed border-[var(--mm-border)] bg-[var(--mm-surface2)]/35 px-3 py-2 text-xs text-[var(--mm-text2)]">
          Save this server on the Connection tab first to turn on these
          controls.
        </p>
      ) : null}
      <div
        className="space-y-2 rounded-md border border-[var(--mm-border)] bg-[var(--mm-card-bg)] px-4 py-3 text-sm text-[var(--mm-text)]"
        data-testid="pruner-run-limits-panel"
      >
        <p className="text-sm font-semibold text-[var(--mm-text)]">
          How many items each scan may check
        </p>
        <p
          className="text-xs text-[var(--mm-text2)]"
          data-testid="pruner-delete-cap-note"
        >
          This limit only affects how many rows MediaMop lists for you to
          review. Deleting still uses exactly the list you confirmed, not a
          fresh scan.
        </p>
        {showInteractiveControls ? (
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-xs text-[var(--mm-text2)]">
              Max items per scan (1-5000)
              <input
                type="number"
                min={1}
                max={5000}
                value={previewMaxItems}
                disabled={busy}
                onChange={(e) =>
                  setPreviewMaxItems(
                    Math.max(1, Math.min(5000, Number(e.target.value) || 500)),
                  )
                }
                className="ml-2 w-24 rounded border border-[var(--mm-border)] bg-[var(--mm-surface2)] px-2 py-1 text-sm text-[var(--mm-text)]"
              />
            </label>
            <button
              type="button"
              className="rounded-md border border-[var(--mm-border)] px-3 py-1 text-sm font-medium text-[var(--mm-text)] disabled:opacity-50"
              disabled={busy}
              onClick={() => void savePreviewMaxItemsSettings()}
            >
              Save run limits
            </button>
            {previewMaxItemsMsg ? (
              <p className="text-xs text-green-600">{previewMaxItemsMsg}</p>
            ) : null}
          </div>
        ) : (
          <p className="text-xs text-[var(--mm-text2)]">
            Max items per scan: <strong>{scopePreviewMaxItems ?? "—"}</strong>.
            Sign in as an operator to edit.
          </p>
        )}
      </div>
      <div
        className="rounded-md border border-[var(--mm-border)] bg-[var(--mm-surface2)]/40 px-4 py-3 text-xs text-[var(--mm-text2)] sm:text-sm"
        data-testid="pruner-scope-trust-banner"
      >
        <p>
          Each scan saves a fixed list you can review. Deleting uses only that
          saved list, not a new pass over the library.
        </p>
      </div>
      {!isPlex ? (
        <p className="text-sm text-[var(--mm-text2)]">
          {scope === "tv"
            ? "Scans can list episodes missing a main image, or episodes never played for your MediaMop user that are older than the age you set. Each cleanup type has its own button above."
            : "Scans can list movies missing a main poster, movies marked watched for your MediaMop user, or movies never watched and older than the age you set. Each cleanup type has its own button above."}
        </p>
      ) : (
        <p className="text-sm text-[var(--mm-text2)]">
          On Plex, scans read the same on-server details as Jellyfin and Emby:
          broken posters look for missing episode or movie art. Movie scans can
          also find watched titles, low audience scores, and old unwatched
          titles. Deleting only touches the exact titles from the list you
          reviewed; items already gone are counted as skipped. Whether Plex
          removes files or only metadata depends on your Plex server.
        </p>
      )}
      {isPlex ? (
        <p
          className="text-xs text-[var(--mm-text2)]"
          data-testid="pruner-plex-preview-cap-note"
        >
          Plex stops each scan at the smaller of your per-tab item limit and a
          built-in safety cap. If a scan says the list was shortened, there
          were more matches than MediaMop showed this time.
        </p>
      ) : null}
      <div>
        <h3
          className="text-base font-semibold text-[var(--mm-text)]"
          data-testid="pruner-filters-section-heading"
        >
          Optional filters for scans
        </h3>
        <p className="text-xs text-[var(--mm-text2)]">
          Filters affect scan results on this {libraryTabPhrase} only.
        </p>
      </div>
    </>
  );
}
