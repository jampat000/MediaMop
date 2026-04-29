import { fetchCsrfToken } from "../api/auth-api";
import { apiFetch, readJson, requireOk } from "../api/client";
import type {
  RefinerWatchedFolderRemuxScanDispatchEnqueueBody,
  RefinerWatchedFolderRemuxScanDispatchEnqueueOut,
} from "./types";

export const refinerWatchedFolderRemuxScanDispatchEnqueuePath = () =>
  "/api/v1/refiner/jobs/watched-folder-remux-scan-dispatch/enqueue";

export async function postRefinerWatchedFolderRemuxScanDispatchEnqueue(
  body: RefinerWatchedFolderRemuxScanDispatchEnqueueBody,
): Promise<RefinerWatchedFolderRemuxScanDispatchEnqueueOut> {
  const csrf_token = await fetchCsrfToken();
  const path = refinerWatchedFolderRemuxScanDispatchEnqueuePath();
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, csrf_token }),
  });
  await requireOk(path, r, "Could not queue watched-folder scan");
  return readJson<RefinerWatchedFolderRemuxScanDispatchEnqueueOut>(r);
}
