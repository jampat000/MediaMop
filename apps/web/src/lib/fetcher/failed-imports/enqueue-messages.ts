import type { FailedImportEnqueueOut } from "./types";

/** After queueing a Radarr/Sonarr download-queue failed-import pass. */

export function failedImportEnqueueResultMessage(out: FailedImportEnqueueOut): string {
  if (out.enqueue_outcome === "created") {
    return "Queued now — a new failed-import pass was recorded.";
  }
  return "Already queued — the existing failed-import pass was reused (no duplicate).";
}
