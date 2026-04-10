import type { ManualCleanupDriveEnqueueOut } from "./types";

/** User-facing result line for manual cleanup-drive enqueue. */

export function manualCleanupEnqueueResultMessage(out: ManualCleanupDriveEnqueueOut): string {
  if (out.enqueue_outcome === "created") {
    return "Enqueued now — a new cleanup-drive job entry was recorded.";
  }
  return "Already queued — the existing cleanup-drive job entry was reused (no duplicate row).";
}
