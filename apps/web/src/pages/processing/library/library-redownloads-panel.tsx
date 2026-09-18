/**
 * Issue #509's "titles missing tracks your new rules keep", moved onto #568's Problems sub-view: a past clean
 * removed a track the current rules would keep, and the only way back is downloading the title again.
 *
 * Rule 3 of docs/design/content-language.md: the titles are a hairline-separated list, not a stack of boxes.
 * "Download again" only opens the confirmation, so it is a quiet link; the confirmation itself keeps its real
 * buttons and its own wording untouched.
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
      className="mm-quiet-section"
      aria-labelledby="library-redownloads-heading"
      data-testid="library-redownloads-section"
    >
      <div className="mm-quiet-section__head">
        <h3
          id="library-redownloads-heading"
          className="mm-quiet-section__title"
        >
          Titles missing tracks your new rules keep
        </h3>
      </div>
      <div className="mm-quiet-section__body">
        <p className="mm-quiet-note">
          A past clean removed these tracks for good; the only way to get one
          back is downloading the title again.
        </p>
        <ul className="mt-3">
          {titles.map((title) => (
            <li
              key={title.path}
              className="border-b border-[var(--mm-border)] py-3 text-sm last:border-b-0"
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
                    className="mm-quiet-link"
                    onClick={() => setConfirming(title.path)}
                  >
                    Download again →
                  </button>
                ) : (
                  <span className="text-xs text-[var(--mm-text3)]">
                    {title.unavailable_reason}
                  </span>
                )}
              </div>
              {confirming === title.path ? (
                <div className="mt-3 space-y-2 border-l-2 border-[var(--mm-border)] pl-3">
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
          <p
            className="mt-3 text-sm text-[var(--mm-status-failed-text)]"
            role="alert"
          >
            {error}
          </p>
        ) : null}
      </div>
    </section>
  );
}
