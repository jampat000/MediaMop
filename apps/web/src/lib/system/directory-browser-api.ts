import { apiFetch, readJson, requireOk } from "../api/client";

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
  const apiPath = `/api/v1/system/directories${qs}`;
  const r = await apiFetch(apiPath);
  await requireOk(apiPath, r, "Could not browse folders");
  return readJson<DirectoryBrowseResponse>(r);
}
