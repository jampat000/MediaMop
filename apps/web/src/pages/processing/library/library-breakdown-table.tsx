/**
 * Issue #568: one breakdown as a sortable table with a share bar per row, plus a "Show files" link that
 * filters the Files sub-view by that value. The rows are the distinct values of one facet (tens of rows at
 * most, already aggregated by the server), so sorting them here is cheap and never touches the file list.
 *
 * Rule 3 of docs/design/content-language.md: a heading, a hairline, then the content — no box, and the
 * table is `.mm-quiet-table --sortable`. Below 760px that primitive stacks each row and reads the column
 * name from `data-label`; the `--sortable` variant keeps the header row above the stack as a row of sort
 * controls, so these buttons are reachable at every width rather than being a pointer-width affordance.
 */
import { useMemo, useState } from "react";

import {
  formatBytes,
  libraryFacetValueLabel,
  type LibraryBreakdownRow,
  type LibraryFacet,
} from "../../../lib/processing/library-api";

type BreakdownSort = "value" | "files" | "size";

export type LibraryBreakdownTableProps = {
  facet: LibraryFacet;
  heading: string;
  rows: LibraryBreakdownRow[];
  /** Opens the Files sub-view filtered to one value of this facet. */
  onShowFiles: (facet: LibraryFacet, value: string) => void;
  /** What to say when this library has nothing to break down yet. */
  emptyMessage: string;
};

function columnLabel(facet: LibraryFacet): string {
  switch (facet) {
    case "video_codec":
      return "Codec";
    case "resolution":
      return "Resolution";
    case "audio":
      return "Codec and channels";
    default:
      return "Language";
  }
}

export function LibraryBreakdownTable({
  facet,
  heading,
  rows,
  onShowFiles,
  emptyMessage,
}: LibraryBreakdownTableProps) {
  const [sort, setSort] = useState<BreakdownSort>("files");
  const [descending, setDescending] = useState(true);
  const headingId = `library-breakdown-${facet}-heading`;

  const sorted = useMemo(() => {
    const copy = [...rows];
    copy.sort((a, b) => {
      const order =
        sort === "value"
          ? libraryFacetValueLabel(facet, a.value).localeCompare(
              libraryFacetValueLabel(facet, b.value),
            )
          : sort === "size"
            ? a.size_bytes - b.size_bytes
            : a.files - b.files;
      return descending ? -order : order;
    });
    return copy;
  }, [rows, sort, descending, facet]);

  const toggle = (next: BreakdownSort) => {
    if (next === sort) {
      setDescending((previous) => !previous);
    } else {
      setSort(next);
      setDescending(next !== "value");
    }
  };

  const header = (key: BreakdownSort, label: string) => (
    <th
      scope="col"
      aria-sort={
        sort === key ? (descending ? "descending" : "ascending") : "none"
      }
    >
      <button
        type="button"
        className="inline-flex items-center gap-1 hover:text-[var(--mm-text1)]"
        onClick={() => toggle(key)}
      >
        {label}
        <span aria-hidden="true">
          {sort === key ? (descending ? "▾" : "▴") : ""}
        </span>
      </button>
    </th>
  );

  return (
    <section
      className="mm-quiet-section"
      aria-labelledby={headingId}
      data-testid={`library-breakdown-${facet}`}
    >
      <div className="mm-quiet-section__head">
        <h3 id={headingId} className="mm-quiet-section__title">
          {heading}
        </h3>
      </div>
      <div className="mm-quiet-section__body">
        {rows.length === 0 ? (
          <p className="mm-quiet-note">{emptyMessage}</p>
        ) : (
          <div className="mm-quiet-table-wrap">
            <table className="mm-quiet-table mm-quiet-table--sortable min-w-[30rem] max-[760px]:min-w-0">
              <thead>
                <tr>
                  {header("value", columnLabel(facet))}
                  {header("files", "Files")}
                  {header("size", "Size")}
                  <th scope="col">Share</th>
                  <th scope="col">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((row) => (
                  <tr key={row.value} data-testid="library-breakdown-row">
                    <th scope="row" className="mm-quiet-table__name">
                      {libraryFacetValueLabel(facet, row.value)}
                    </th>
                    <td data-label="Files" className="tabular-nums">
                      {row.files}
                    </td>
                    <td data-label="Size" className="tabular-nums">
                      {formatBytes(row.size_bytes)}
                    </td>
                    <td data-label="Share">
                      <div className="flex items-center gap-2">
                        <div
                          className="h-2 min-w-[3rem] flex-1 overflow-hidden rounded-full bg-[var(--mm-well-bg)]"
                          role="presentation"
                        >
                          <div
                            className="h-full rounded-full bg-[var(--mm-accent)]"
                            style={{
                              width: `${Math.max(2, Math.round(row.share * 100))}%`,
                            }}
                          />
                        </div>
                        <span className="w-10 shrink-0 text-right text-xs tabular-nums text-[var(--mm-text3)]">
                          {Math.round(row.share * 100)}%
                        </span>
                      </div>
                    </td>
                    <td data-label="">
                      <button
                        type="button"
                        className="mm-quiet-link"
                        onClick={() => onShowFiles(facet, row.value)}
                      >
                        Show files →
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
