/**
 * Issue #568: one breakdown as a sortable table with a share bar per row, plus a "Show files" link that
 * filters the Files sub-view by that value. The rows are the distinct values of one facet (tens of rows at
 * most, already aggregated by the server), so sorting them here is cheap and never touches the file list.
 */
import { useMemo, useState } from "react";

import {
  formatBytes,
  libraryFacetValueLabel,
  type LibraryBreakdownRow,
  type LibraryFacet,
} from "../../../lib/processing/library-api";
import { mmActionButtonClass } from "../../../lib/ui/mm-control-roles";

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

  const header = (key: BreakdownSort, label: string, className = "") => (
    <th
      className={`py-1 font-medium ${className}`}
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
      className="mm-bubble space-y-2 p-4"
      data-testid={`library-breakdown-${facet}`}
    >
      <h3 className="text-sm font-semibold text-[var(--mm-text1)]">
        {heading}
      </h3>
      {rows.length === 0 ? (
        <p className="text-sm text-[var(--mm-text3)]">{emptyMessage}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[26rem] text-left text-sm">
            <thead>
              <tr className="border-b border-[var(--mm-border)] text-[var(--mm-text3)]">
                {header("value", columnLabel(facet))}
                {header("files", "Files", "w-20 text-right")}
                {header("size", "Size", "w-28 text-right")}
                <th className="w-40 py-1 font-medium" scope="col">
                  Share
                </th>
                <th className="w-28 py-1" scope="col">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((row) => (
                <tr
                  key={row.value}
                  className="border-b border-[var(--mm-border)]/50"
                  data-testid="library-breakdown-row"
                >
                  <td className="py-1.5 text-[var(--mm-text1)]">
                    {libraryFacetValueLabel(facet, row.value)}
                  </td>
                  <td className="py-1.5 text-right tabular-nums">
                    {row.files}
                  </td>
                  <td className="py-1.5 text-right tabular-nums text-[var(--mm-text2)]">
                    {formatBytes(row.size_bytes)}
                  </td>
                  <td className="py-1.5">
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
                  <td className="py-1.5 text-right">
                    <button
                      type="button"
                      className={mmActionButtonClass({ variant: "tertiary" })}
                      onClick={() => onShowFiles(facet, row.value)}
                    >
                      Show files
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
