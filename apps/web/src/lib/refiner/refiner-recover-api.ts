import { fetchCsrfToken } from "../api/auth-api";
import { apiFetch, readJson } from "../api/client";

export type RecoverFinalizeFailureResult = {
  job_id: number;
  status: string;
};

export async function postRecoverFinalizeFailure(jobId: number): Promise<RecoverFinalizeFailureResult> {
  const csrf_token = await fetchCsrfToken();
  const r = await apiFetch(`/api/v1/refiner/jobs/${jobId}/recover-finalize-failure`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm: true, csrf_token }),
  });
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const b = await readJson<{ detail?: string }>(r);
      if (typeof b.detail === "string") {
        detail = b.detail;
      }
    } catch {
      /* ignore */
    }
    throw new Error(detail || `Could not apply manual completion (${r.status})`);
  }
  return readJson<RecoverFinalizeFailureResult>(r);
}
