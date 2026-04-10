import { fetchCsrfToken } from "../../api/auth-api";
import { apiFetch, readJson } from "../../api/client";

export type FailedImportRecoverFinalizeResult = {
  job_id: number;
  status: string;
};

export async function postFailedImportRecoverFinalize(jobId: number): Promise<FailedImportRecoverFinalizeResult> {
  const csrf_token = await fetchCsrfToken();
  const r = await apiFetch(
    `/api/v1/fetcher/failed-imports/tasks/${jobId}/recover-finalize-failure`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirm: true, csrf_token }),
    },
  );
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
  return readJson<FailedImportRecoverFinalizeResult>(r);
}
