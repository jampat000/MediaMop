import type { FailedImportManualQueuePassOut } from "./types";

/** After a manual Radarr/Sonarr failed-import queue pass is recorded (API response). */

export function failedImportManualQueuePassResultMessage(out: FailedImportManualQueuePassOut): string {
  if (out.queue_outcome === "created") {
    return "Added — a new download-queue pass was scheduled for the worker.";
  }
  return "Already on the list — that pass was already waiting or in progress (no duplicate row).";
}
