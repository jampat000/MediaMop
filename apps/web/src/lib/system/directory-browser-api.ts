import { apiErrorDetailToString, apiFetch, readJson } from "../api/client";

export type DirectoryBrowseEntry = {
  name: string;
  path: string;
  kind: "root" | "directory" | string;
  description: string | null;
};

export type DirectoryBrowseResponse = {
  current_path: string | null;
  parent_path: string | null;
  entries: DirectoryBrowseEntry[];
};

export async function fetchServerDirectories(path?: string | null): Promise<DirectoryBrowseResponse> {
  const qs = path?.trim() ? `?path=${encodeURIComponent(path.trim())}` : "";
  const r = await apiFetch(`/api/v1/system/directories${qs}`);
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const body = await readJson<{ detail?: unknown }>(r);
      detail = apiErrorDetailToString(body.detail) || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail || `Could not browse folders (${r.status})`);
  }
  return readJson<DirectoryBrowseResponse>(r);
}
