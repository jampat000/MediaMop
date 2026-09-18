import { fetchCsrfToken } from "../api/auth-api";
import { apiFetch, readJson, requireOk } from "../api/client";
import type {
  ProcessingFileRemuxPassManualEnqueueBody,
  ProcessingFileRemuxPassManualEnqueueOut,
} from "./types";

export const processingFileRemuxPassEnqueuePath = () =>
  "/api/v1/processing/jobs/file-remux-pass/enqueue";

export async function postProcessingFileRemuxPassEnqueue(
  body: ProcessingFileRemuxPassManualEnqueueBody,
): Promise<ProcessingFileRemuxPassManualEnqueueOut> {
  const csrf_token = await fetchCsrfToken();
  const path = processingFileRemuxPassEnqueuePath();
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, csrf_token }),
  });
  await requireOk(path, r, "Could not queue file pass");
  return readJson<ProcessingFileRemuxPassManualEnqueueOut>(r);
}
