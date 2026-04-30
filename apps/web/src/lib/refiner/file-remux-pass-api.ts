import { fetchCsrfToken } from "../api/auth-api";
import { apiFetch, readJson, requireOk } from "../api/client";
import type {
  RefinerFileRemuxPassManualEnqueueBody,
  RefinerFileRemuxPassManualEnqueueOut,
} from "./types";

export const refinerFileRemuxPassEnqueuePath = () =>
  "/api/v1/refiner/jobs/file-remux-pass/enqueue";

export async function postRefinerFileRemuxPassEnqueue(
  body: RefinerFileRemuxPassManualEnqueueBody,
): Promise<RefinerFileRemuxPassManualEnqueueOut> {
  const csrf_token = await fetchCsrfToken();
  const path = refinerFileRemuxPassEnqueuePath();
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, csrf_token }),
  });
  await requireOk(path, r, "Could not queue file pass");
  return readJson<RefinerFileRemuxPassManualEnqueueOut>(r);
}
