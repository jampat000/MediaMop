/**
 * Issue #568's Files sub-view: the library's files as a real table — the manager's matched title, the path,
 * size, a video/audio/subtitle summary and the state with its reason — sortable by any column, filterable by
 * any breakdown facet, multi-selectable for a Clean (which keeps #505's final-removal confirmation and #508's
 * warnings), with a per-file expander showing what the rules would do (the #502 preview).
 *
 * Sorting, filtering and paging are all the server's: the query string goes straight to the endpoint, which
 * answers with one page. Nothing here ever holds a whole library in memory.
 *
 * Rule 3 of docs/design/content-language.md: no box around any of it, and the table is `.mm-quiet-table`.
 * The sub-view is one thing, so it takes no invented heading. Below 760px the primitive stacks each row and
 * reads its column names from `data-label` — nine columns no longer run off the side of a phone, at the cost
 * of the header row, and with it the sort controls and the select-all box. Both are pointer-width
 * conveniences; the filters, the per-row checkboxes, paging and Clean are not, and all still work there.
 */
import { Fragment, useMemo, useState } from "react";

import { PageLoading } from "../../../components/shared/page-loading";
import {
  formatBytes,
  libraryCodecLabel,
  libraryFacetValueLabel,
  libraryResolutionLabel,
  LIBRARY_FACETS,
  LIBRARY_FILE_CLASSIFICATION_LABELS,
  LIBRARY_MANAGER_FILTER_OPTIONS,
  type LibraryBreakdowns,
  type LibraryFacet,
  type LibraryFile,
  type LibraryFileClassification,
  type LibraryFileFilters,
  type LibraryFileSort,
  type LibraryFilesResult,
} from "../../../lib/processing/library-api";
import {
  mmActionButtonClass,
  mmCheckboxControlClass,
  mmEditableTextFieldClass,
  mmSelectFieldClass,
} from "../../../lib/ui/mm-control-roles";
import { LibraryFilePreview } from "./library-file-preview";

const COLUMNS: { key: LibraryFileSort; label: string }[] = [
  { key: "title", label: "Title" },
  { key: "path", label: "Path" },
  { key: "size", label: "Size" },
  { key: "video", label: "Video" },
  { key: "audio", label: "Audio" },
  { key: "subtitles", label: "Subtitles" },
  { key: "state", label: "State" },
];

export type LibraryFilesViewProps = {
  libraryId: number;
  editable: boolean;
  filters: LibraryFileFilters;
  onFiltersChange: (next: LibraryFileFilters) => void;
  files: LibraryFilesResult | undefined;
  loading: boolean;
  /** The facet values to offer in each filter picker, from the library's own breakdowns. */
  breakdowns: LibraryBreakdowns | undefined;
  selected: Set<string>;
  onToggleSelected: (path: string) => void;
  onSelectAllOnPage: (paths: string[], select: boolean) => void;
  onClean: () => void;
  cleaning: boolean;
  cleanError: string | null;
  emptyState: React.ReactNode;
};

function videoCell(file: LibraryFile): string {
  const codec = libraryCodecLabel(file.video_codec);
  const resolution = libraryResolutionLabel(file.resolution_class);
  return resolution === "Unknown" ? codec : `${codec} · ${resolution}`;
}

export function LibraryFilesView({
  libraryId,
  editable,
  filters,
  onFiltersChange,
  files,
  loading,
  breakdowns,
  selected,
  onToggleSelected,
  onSelectAllOnPage,
  onClean,
  cleaning,
  cleanError,
  emptyState,
}: LibraryFilesViewProps) {
  const [expanded, setExpanded] = useState<string | null>(null);

  const rows = useMemo(() => files?.files ?? [], [files]);
  const selectablePaths = useMemo(
    () =>
      rows
        .filter((f) => f.classification === "would_change")
        .map((f) => f.path),
    [rows],
  );
  const allOnPageSelected =
    selectablePaths.length > 0 &&
    selectablePaths.every((path) => selected.has(path));
  const selectedCount = selected.size;

  const setFilter = (patch: Partial<LibraryFileFilters>) =>
    onFiltersChange({ ...filters, ...patch, page: 1 });

  const setFacet = (facet: LibraryFacet, value: string) =>
    onFiltersChange({
      ...filters,
      facets: { ...filters.facets, [facet]: value || undefined },
      page: 1,
    });

  const sortBy = (key: LibraryFileSort) =>
    onFiltersChange({
      ...filters,
      sort: key,
      direction:
        filters.sort === key && filters.direction !== "desc" ? "desc" : "asc",
      page: 1,
    });

  const activeFacets = LIBRARY_FACETS.filter(
    (facet) => filters.facets?.[facet],
  );
  const pageSize = files?.page_size ?? filters.page_size ?? 50;
  const page = files?.page ?? 1;
  const total = files?.total ?? 0;
  const lastPage = Math.max(1, Math.ceil(total / pageSize));

  return (
    <section
      className="flex w-full min-w-0 flex-col gap-4"
      data-testid="library-files-section"
    >
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-xs font-medium text-[var(--mm-text3)]">
          State
          <select
            className={mmSelectFieldClass}
            style={{ maxWidth: "13rem" }}
            value={filters.classification ?? ""}
            onChange={(e) =>
              setFilter({
                classification:
                  (e.target.value as LibraryFileClassification) || undefined,
              })
            }
          >
            <option value="">All files</option>
            {(
              Object.keys(
                LIBRARY_FILE_CLASSIFICATION_LABELS,
              ) as LibraryFileClassification[]
            ).map((value) => (
              <option key={value} value={value}>
                {LIBRARY_FILE_CLASSIFICATION_LABELS[value]}
              </option>
            ))}
          </select>
        </label>

        {LIBRARY_FACETS.map((facet) => (
          <label
            key={facet}
            className="text-xs font-medium text-[var(--mm-text3)]"
          >
            {
              {
                video_codec: "Video codec",
                resolution: "Resolution",
                audio: "Audio",
                audio_language: "Audio language",
                subtitle_language: "Subtitle language",
              }[facet]
            }
            <select
              className={mmSelectFieldClass}
              style={{ maxWidth: "11rem" }}
              value={filters.facets?.[facet] ?? ""}
              aria-label={`Filter by ${facet.replace(/_/g, " ")}`}
              onChange={(e) => setFacet(facet, e.target.value)}
            >
              <option value="">Any</option>
              {(breakdowns?.[facet] ?? []).map((row) => (
                <option key={row.value} value={row.value}>
                  {libraryFacetValueLabel(facet, row.value)} ({row.files})
                </option>
              ))}
            </select>
          </label>
        ))}

        <label className="text-xs font-medium text-[var(--mm-text3)]">
          Manager
          <select
            className={mmSelectFieldClass}
            style={{ maxWidth: "10rem" }}
            value={filters.manager ?? ""}
            aria-label="Filter by manager"
            onChange={(e) =>
              setFilter({ manager: e.target.value || undefined })
            }
          >
            <option value="">All managers</option>
            {LIBRARY_MANAGER_FILTER_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="text-xs font-medium text-[var(--mm-text3)]">
          Search
          <input
            className={mmEditableTextFieldClass}
            style={{ maxWidth: "18rem" }}
            placeholder="Path or title"
            value={filters.q ?? ""}
            onChange={(e) => setFilter({ q: e.target.value || undefined })}
          />
        </label>
      </div>

      {activeFacets.length > 0 || filters.problem ? (
        <div
          className="flex flex-wrap items-center gap-2 text-xs"
          data-testid="library-files-active-filters"
        >
          <span className="text-[var(--mm-text3)]">Showing only:</span>
          {filters.problem ? (
            <button
              type="button"
              className={mmActionButtonClass({ variant: "tertiary" })}
              onClick={() =>
                onFiltersChange({ ...filters, problem: undefined, page: 1 })
              }
            >
              {filters.problem.replace(/_/g, " ")} ✕
            </button>
          ) : null}
          {activeFacets.map((facet) => (
            <button
              key={facet}
              type="button"
              className={mmActionButtonClass({ variant: "tertiary" })}
              onClick={() => setFacet(facet, "")}
            >
              {libraryFacetValueLabel(facet, filters.facets![facet]!)} ✕
            </button>
          ))}
        </div>
      ) : null}

      {files ? (
        <p className="mm-quiet-note" data-testid="library-files-summary">
          {files.summary.matches} match the rules, {files.summary.would_change}{" "}
          would change, {files.summary.cannot_process} cannot be processed.
          Estimated size saved if all &quot;would change&quot; files were
          cleaned: {formatBytes(files.summary.estimated_bytes_saved)}.
          {total !== files.summary.files
            ? ` These filters show ${total} of ${files.summary.files} files.`
            : ""}
        </p>
      ) : null}

      {loading ? <PageLoading label="Loading files…" /> : null}

      {files && rows.length === 0 ? emptyState : null}

      {files && rows.length > 0 ? (
        <div className="mm-quiet-table-wrap">
          <table className="mm-quiet-table min-w-[58rem] max-[760px]:min-w-0">
            <thead>
              <tr>
                <th scope="col">
                  {editable ? (
                    <input
                      type="checkbox"
                      className={mmCheckboxControlClass}
                      checked={allOnPageSelected}
                      disabled={selectablePaths.length === 0}
                      aria-label="Select every changeable file on this page"
                      onChange={() =>
                        onSelectAllOnPage(selectablePaths, !allOnPageSelected)
                      }
                    />
                  ) : null}
                </th>
                {COLUMNS.map((column) => (
                  <th
                    key={column.key}
                    scope="col"
                    aria-sort={
                      files.sort === column.key
                        ? files.direction === "desc"
                          ? "descending"
                          : "ascending"
                        : "none"
                    }
                  >
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 hover:text-[var(--mm-text1)]"
                      onClick={() => sortBy(column.key)}
                    >
                      {column.label}
                      <span aria-hidden="true">
                        {files.sort === column.key
                          ? files.direction === "desc"
                            ? "▾"
                            : "▴"
                          : ""}
                      </span>
                    </button>
                  </th>
                ))}
                <th scope="col">
                  <span className="sr-only">Details</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((file) => (
                <Fragment key={file.path}>
                  <tr data-testid="library-file-row">
                    <td data-label="">
                      <input
                        type="checkbox"
                        className={mmCheckboxControlClass}
                        checked={selected.has(file.path)}
                        onChange={() => onToggleSelected(file.path)}
                        disabled={
                          !editable || file.classification !== "would_change"
                        }
                        aria-label={`Select ${file.path}`}
                      />
                    </td>
                    <th scope="row" className="mm-quiet-table__name">
                      {file.manager_title ?? "Unmatched"}
                      {file.manager_title && file.manager_kind ? (
                        <span className="text-xs font-normal text-[var(--mm-text3)]">
                          {" "}
                          ({file.manager_kind})
                        </span>
                      ) : null}
                    </th>
                    <td data-label="Path" className="[overflow-wrap:anywhere]">
                      {file.path}
                    </td>
                    <td
                      data-label="Size"
                      className="tabular-nums whitespace-nowrap"
                    >
                      {formatBytes(file.size_bytes)}
                    </td>
                    <td data-label="Video">{videoCell(file)}</td>
                    <td data-label="Audio">
                      {file.audio_summary ?? "Unknown"}
                    </td>
                    <td data-label="Subtitles">
                      {file.subtitle_summary ?? "None"}
                    </td>
                    <td data-label="State">
                      <span className="mm-quiet-table__strong">
                        {
                          LIBRARY_FILE_CLASSIFICATION_LABELS[
                            file.classification
                          ]
                        }
                      </span>
                      <span className="mm-quiet-table__sub">
                        {file.summary ?? file.reason ?? ""}
                      </span>
                    </td>
                    <td data-label="">
                      <button
                        type="button"
                        className="mm-quiet-link"
                        aria-expanded={expanded === file.path}
                        onClick={() =>
                          setExpanded(expanded === file.path ? null : file.path)
                        }
                      >
                        {expanded === file.path ? "Hide" : "Details"}
                      </button>
                    </td>
                  </tr>
                  {expanded === file.path ? (
                    <tr>
                      <td colSpan={COLUMNS.length + 2} data-label="">
                        <LibraryFilePreview
                          libraryId={libraryId}
                          path={file.path}
                        />
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {total > pageSize ? (
        <div
          className="flex flex-wrap items-center gap-2 text-sm text-[var(--mm-text2)]"
          data-testid="library-files-paging"
        >
          <button
            type="button"
            className={mmActionButtonClass({
              variant: "tertiary",
              disabled: page <= 1,
            })}
            disabled={page <= 1}
            onClick={() => onFiltersChange({ ...filters, page: page - 1 })}
          >
            Previous
          </button>
          <span>
            Page {page} of {lastPage}
          </span>
          <button
            type="button"
            className={mmActionButtonClass({
              variant: "tertiary",
              disabled: page >= lastPage,
            })}
            disabled={page >= lastPage}
            onClick={() => onFiltersChange({ ...filters, page: page + 1 })}
          >
            Next
          </button>
        </div>
      ) : null}

      {editable ? (
        <button
          type="button"
          className={mmActionButtonClass({
            variant: "primary",
            disabled: selectedCount === 0 || cleaning,
          })}
          disabled={selectedCount === 0 || cleaning}
          onClick={onClean}
          data-testid="library-clean-button"
        >
          Clean selected ({selectedCount})
        </button>
      ) : null}
      {cleanError ? (
        <p className="text-sm text-[var(--mm-status-failed-text)]" role="alert">
          {cleanError}
        </p>
      ) : null}
    </section>
  );
}
