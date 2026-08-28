import { fetchCsrfToken } from "../api/auth-api";
import { apiFetch, readJson, requireOk } from "../api/client";

export type RefinerMediaScope = "movie" | "tv";

export const REFINER_MEDIA_SCOPE_LABELS: Record<RefinerMediaScope, string> = {
  movie: "Movies",
  tv: "TV episodes",
};

/** One configured Refiner library. Adding one is a POST, not a schema change. */
export interface RefinerLibrary {
  id: number;
  name: string;
  enabled: boolean;
  media_scope: RefinerMediaScope;
  display_order: number;

  watched_folder: string;
  work_folder: string;
  output_folder: string;

  media_extensions_csv: string;
  exclude_markers_csv: string;
  include_patterns_csv: string;
  exclude_patterns_csv: string;
  min_file_size_mb: number;
  max_file_size_mb: number;
  min_file_age_seconds: number;
  exclude_hidden: boolean;
  top_level_only: boolean;

  scan_interval_seconds: number;
  hold_minutes: number;
  file_detection_interval_seconds: number;
  ignore_size_changes: boolean;
  skip_access_tests: boolean;
  schedule_enabled: boolean;
  schedule_hours_limited: boolean;
  schedule_days: string;
  schedule_start: string;
  schedule_end: string;

  max_concurrent_files: number;
  priority: number;

  rule_set_id: number | null;
  manager_connection_ids: number[];
  discovered_from_connection_id: number | null;
  discovered_library_key: string | null;
  /** Queued or running jobs. Deletion is refused while this is non-zero. */
  active_job_count: number;
  updated_at: string | null;
}

export interface RefinerLibraryWrite {
  name: string;
  media_scope: RefinerMediaScope;
  enabled?: boolean;
  watched_folder?: string;
  work_folder?: string;
  output_folder?: string;
  media_extensions_csv?: string;
  exclude_markers_csv?: string;
  include_patterns_csv?: string;
  exclude_patterns_csv?: string;
  min_file_size_mb?: number;
  max_file_size_mb?: number;
  min_file_age_seconds?: number;
  exclude_hidden?: boolean;
  top_level_only?: boolean;
  scan_interval_seconds?: number;
  hold_minutes?: number;
  file_detection_interval_seconds?: number;
  ignore_size_changes?: boolean;
  skip_access_tests?: boolean;
  schedule_enabled?: boolean;
  schedule_hours_limited?: boolean;
  schedule_days?: string;
  schedule_start?: string;
  schedule_end?: string;
  max_concurrent_files?: number;
  priority?: number;
  rule_set_id?: number | null;
  manager_connection_ids?: number[];
}

export interface RefinerRuleSet {
  id: number;
  name: string;
  primary_audio_lang: string;
  secondary_audio_lang: string;
  tertiary_audio_lang: string;
  default_audio_slot: string;
  remove_commentary: boolean;
  subtitle_mode: string;
  subtitle_langs_csv: string;
  preserve_forced_subs: boolean;
  preserve_default_subs: boolean;
  audio_preference_mode: string;
  /** Libraries pointing at this rule set. Deleting one still in use is refused. */
  used_by_library_count: number;
  updated_at: string | null;
}

export const refinerLibrariesPath = () => "/api/v1/refiner/libraries";
const libraryPath = (id: number) => `${refinerLibrariesPath()}/${id}`;

export async function fetchRefinerLibraries(): Promise<RefinerLibrary[]> {
  const path = refinerLibrariesPath();
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load Refiner libraries");
  return readJson<RefinerLibrary[]>(r);
}

export async function createRefinerLibrary(
  data: RefinerLibraryWrite,
): Promise<RefinerLibrary> {
  const csrf_token = await fetchCsrfToken();
  const path = refinerLibrariesPath();
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...data, csrf_token }),
  });
  await requireOk(path, r, "Could not add that library");
  return readJson<RefinerLibrary>(r);
}

export async function updateRefinerLibrary(
  id: number,
  data: RefinerLibraryWrite,
): Promise<RefinerLibrary> {
  const csrf_token = await fetchCsrfToken();
  const path = libraryPath(id);
  const r = await apiFetch(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...data, csrf_token }),
  });
  await requireOk(path, r, "Could not save that library");
  return readJson<RefinerLibrary>(r);
}

export async function deleteRefinerLibrary(id: number): Promise<void> {
  const csrf_token = await fetchCsrfToken();
  const path = libraryPath(id);
  const r = await apiFetch(path, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token }),
  });
  // 409 carries the refusal reason — queued work, which the operator can act on.
  await requireOk(path, r, "Could not remove that library");
}

export async function reorderRefinerLibraries(
  library_ids_in_order: number[],
): Promise<RefinerLibrary[]> {
  const csrf_token = await fetchCsrfToken();
  const path = `${refinerLibrariesPath()}/reorder`;
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ library_ids_in_order, csrf_token }),
  });
  await requireOk(path, r, "Could not reorder libraries");
  return readJson<RefinerLibrary[]>(r);
}
