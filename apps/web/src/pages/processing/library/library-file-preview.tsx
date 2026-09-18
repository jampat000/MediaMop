/**
 * Issue #568's per-file expander: what this library's rules would do to one file, track by track. It reuses
 * the #502 "try on a file" preview endpoint (`POST .../preview` with the file's absolute path) rather than a
 * second implementation of the same explanation — so the row an operator opens here says exactly what the
 * rule-set editor's own preview would say about it.
 */
import { useQuery } from "@tanstack/react-query";

import { previewProcessingRules } from "../../../lib/processing/rules-preview-api";
import { processingStreamLanguageLabel } from "../../../lib/processing/stream-language-options";
import { formatBytes } from "../../../lib/processing/library-api";

export type LibraryFilePreviewProps = {
  libraryId: number;
  path: string;
};

export function LibraryFilePreview({
  libraryId,
  path,
}: LibraryFilePreviewProps) {
  const preview = useQuery({
    queryKey: ["processing", "library-file-preview", libraryId, path],
    queryFn: () => previewProcessingRules({ libraryId, absolutePath: path }),
    // A preview runs a real ffprobe on a real file, so it is asked for once per opened row, not on a timer.
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  if (preview.isPending) {
    return (
      <p
        className="text-sm text-[var(--mm-text3)]"
        data-testid="library-file-preview-loading"
      >
        Reading the file’s tracks…
      </p>
    );
  }

  if (preview.isError) {
    return (
      <p className="text-sm text-[var(--mm-status-failed-text)]" role="alert">
        {(preview.error as Error).message}
      </p>
    );
  }

  const result = preview.data;
  return (
    <div className="space-y-2" data-testid="library-file-preview">
      <p className="text-sm text-[var(--mm-text2)]">
        {result.remux_required
          ? "These rules would change this file:"
          : "These rules would leave this file exactly as it is."}
        {result.estimated_size_reduction_bytes
          ? ` About ${formatBytes(result.estimated_size_reduction_bytes)} smaller (an estimate).`
          : ""}
      </p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[32rem] text-left text-sm">
          <thead>
            <tr className="border-b border-[var(--mm-border)] text-[var(--mm-text3)]">
              <th className="py-1 font-medium" scope="col">
                Track
              </th>
              <th className="py-1 font-medium" scope="col">
                Language
              </th>
              <th className="py-1 font-medium" scope="col">
                Codec
              </th>
              <th className="py-1 font-medium" scope="col">
                What the rules do
              </th>
            </tr>
          </thead>
          <tbody>
            {result.tracks.map((track) => (
              <tr
                key={`${track.type}-${track.index}`}
                className="border-b border-[var(--mm-border)]/50 align-top"
                data-testid="library-file-preview-track"
              >
                <td className="py-1.5 text-[var(--mm-text2)]">
                  {track.type}
                  {track.default ? " · default" : ""}
                  {track.forced ? " · forced" : ""}
                </td>
                <td className="py-1.5">
                  {processingStreamLanguageLabel(track.language)}
                </td>
                <td className="py-1.5 text-[var(--mm-text2)]">
                  {track.codec}
                  {track.channels ? ` · ${track.channels}ch` : ""}
                </td>
                <td className="py-1.5">
                  <span
                    className={
                      track.action === "keep"
                        ? "text-[var(--mm-status-healthy-text)]"
                        : "text-[var(--mm-status-warning-text)]"
                    }
                  >
                    {track.action === "keep" ? "Keep" : "Remove"}
                  </span>
                  {track.reasons.length > 0 ? (
                    <span className="text-[var(--mm-text3)]">
                      {" "}
                      — {track.reasons.join(" ")}
                    </span>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {result.notes.concat(result.metadata_notes).map((note) => (
        <p key={note} className="text-xs text-[var(--mm-text3)]">
          {note}
        </p>
      ))}
    </div>
  );
}
