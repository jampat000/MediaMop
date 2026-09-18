import { fetchCsrfToken } from "../api/auth-api";
import { apiFetch, readJson, requireOk } from "../api/client";
import type {
  ProcessingWatchedFolderRemuxScanDispatchEnqueueBody,
  ProcessingWatchedFolderRemuxScanDispatchEnqueueOut,
} from "./types";

export const processingWatchedFolderRemuxScanDispatchEnqueuePath = () =>
  "/api/v1/processing/jobs/watched-folder-remux-scan-dispatch/enqueue";

export async function postProcessingWatchedFolderRemuxScanDispatchEnqueue(
  body: ProcessingWatchedFolderRemuxScanDispatchEnqueueBody,
): Promise<ProcessingWatchedFolderRemuxScanDispatchEnqueueOut> {
  const csrf_token = await fetchCsrfToken();
  const path = processingWatchedFolderRemuxScanDispatchEnqueuePath();
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, csrf_token }),
  });
  await requireOk(path, r, "Could not queue watched-folder scan");
  return readJson<ProcessingWatchedFolderRemuxScanDispatchEnqueueOut>(r);
}
