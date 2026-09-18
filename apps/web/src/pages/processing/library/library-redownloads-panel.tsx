/**
 * Issue #509's "titles missing tracks your new rules keep", moved onto #568's Problems sub-view: a past clean
 * removed a track the current rules would keep, and the only way back is downloading the title again.
 */
import { useState } from "react";

import type { LibraryRedownloadTitle } from "../../../lib/processing/library-api";
import { mmActionButtonClass } from "../../../lib/ui/mm-control-roles";

export type LibraryRedownloadsPanelProps = {
  titles: LibraryRedownloadTitle[];
  editable: boolean;
  requesting: boolean;
  error: string | null;
  onRequest: (path: string, onDone: () => void) => void;
};

export function LibraryRedownloadsPanel({
  titles,
  editable,
  requesting,
  error,
  onRequest,
}: LibraryRedownloadsPanelProps) {
  const [confirming, setConfirming] = useState<string | null>(null);

  if (titles.length === 0) {
    return null;
  }

  return (
    <section
      className="mm-bubble space-y-3 p-4"
      data-testid="library-redownloads-section"
    >
      <h3 className="text-sm font-semibold text-[var(--mm-text1)]">
        Titles missing tracks your new rules keep
      </h3>
      <p className="text-xs text-[var(--mm-text3)]">
        A past clean removed these tracks for good; the only way to get one back
        is downloading the title again.
      </p>
      <ul className="space-y-2">
        {titles.map((title) => (
          <li
            key={title.path}
            className="rounded border border-[var(--mm-border)] p-2 text-sm"
            data-testid="library-redownload-row"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="break-all font-medium text-[var(--mm-text1)]">
                  {title.manager_title ?? title.path}
                </div>
                <div className="text-xs text-[var(--mm-text3)]">
                  {title.removed_tracks
                    .map((t) => `${t.language} ${t.type}`)
                    .join(", ")}
                </div>
              </div>
              {editable && title.can_redownload ? (
                <button
                  type="button"
                  className={mmActionButtonClass({ variant: "secondary" })}
                  onClick={() => setConfirming(title.path)}
                >
                  Download again
                </button>
              ) : (
                <span className="text-xs text-[var(--mm-text3)]">
                  {title.unavailable_reason}
                </span>
              )}
            </div>
            {confirming === title.path ? (
              <div className="mt-2 space-y-2 border-t border-[var(--mm-border)] pt-2">
                <p className="text-sm text-[var(--mm-status-failed-text)]">
                  {title.confirmation_message}
                </p>
                <div className="flex gap-2">
                  <button
                    type="button"
                    className={mmActionButtonClass({
                      variant: "primary",
                      disabled: requesting,
                    })}
                    disabled={requesting}
                    onClick={() =>
                      onRequest(title.path, () => setConfirming(null))
                    }
                  >
                    {requesting ? "Requesting…" : "Confirm download again"}
                  </button>
                  <button
                    type="button"
                    className={mmActionButtonClass({ variant: "tertiary" })}
                    onClick={() => setConfirming(null)}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : null}
          </li>
        ))}
      </ul>
      {error ? (
        <p className="text-sm text-[var(--mm-status-failed-text)]" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}
