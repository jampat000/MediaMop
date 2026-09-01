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
  rejected_file_action: "leave" | "delete_file";
  min_file_age_seconds: number;
  created_after: string | null;
  created_before: string | null;
  modified_after: string | null;
  modified_before: string | null;
  exclude_hidden: boolean;
  top_level_only: boolean;

  scan_interval_seconds: number;
  hold_minutes: number;
  /** Files beside the video that travel with it, renamed to the output's stem. Empty migrates nothing. */
  sidecar_patterns_csv: string;
  preserve_original_timestamps: boolean;
  /** What to do when an output already exists at the same path. "replace" is the long-standing behaviour. */
  output_collision_policy: string;
  /** Hardware decoding. A choice that cannot work falls back to software and records why. */
  hardware_decode_mode: string;
  hardware_device: string;
  hardware_disabled_vendors_csv: string;
  ffmpeg_strictness: string;
  file_detection_interval_seconds: number;
  ignore_size_changes: boolean;
  skip_access_tests: boolean;
  file_system_events_enabled: boolean;
  max_attempts: number;
  retry_backoff_seconds: number;
  retry_execution_failures: boolean;
  retry_preflight_failures: boolean;
  schedule_grid: string;
  schedule_enabled: boolean;
  schedule_hours_limited: boolean;
  schedule_days: string;
  schedule_start: string;
  schedule_end: string;

  max_concurrent_files: number;
  priority: number;

  rule_set_id: number | null;
  manager_connection_ids: number[];
  manager_coverage: "connected" | "no_upstream_signal" | "unreachable" | string;
  manager_coverage_detail: string;
  discovered_from_connection_id: number | null;
  discovered_library_key: string | null;
  /** Queued or running jobs. Deletion is refused while this is non-zero. */
  active_job_count: number;
  updated_at: string | null;
}

export interface RefinerLibraryWrite {
  name: string;
  media_scope: RefinerMediaScope;
  enabled: boolean;
  watched_folder: string;
  work_folder: string;
  output_folder: string;
  media_extensions_csv: string;
  exclude_markers_csv: string;
  include_patterns_csv: string;
  exclude_patterns_csv: string;
  min_file_size_mb: number;
  max_file_size_mb: number;
  rejected_file_action: "leave" | "delete_file";
  min_file_age_seconds: number;
  created_after: string | null;
  created_before: string | null;
  modified_after: string | null;
  modified_before: string | null;
  exclude_hidden: boolean;
  top_level_only: boolean;
  scan_interval_seconds: number;
  hold_minutes: number;
  sidecar_patterns_csv: string;
  preserve_original_timestamps: boolean;
  output_collision_policy: string;
  hardware_decode_mode: string;
  hardware_device: string;
  hardware_disabled_vendors_csv: string;
  ffmpeg_strictness: string;
  file_detection_interval_seconds: number;
  ignore_size_changes: boolean;
  skip_access_tests: boolean;
  file_system_events_enabled: boolean;
  max_attempts: number;
  retry_backoff_seconds: number;
  retry_execution_failures: boolean;
  retry_preflight_failures: boolean;
  schedule_grid: string;
  schedule_enabled: boolean;
  schedule_hours_limited: boolean;
  schedule_days: string;
  schedule_start: string;
  schedule_end: string;
  max_concurrent_files: number;
  priority: number;
  rule_set_id: number | null;
  manager_connection_ids: number[];
}

export interface DiscoverableRefinerLibrary {
  key: string;
  name: string;
  media_scope: RefinerMediaScope | null;
  root_path: string | null;
  already_imported: boolean;
  local_path_problem: string | null;
  processes_before_import: boolean;
  output_path: string | null;
  output_path_problem: string | null;
}

export interface RefinerLibraryDrift {
  kind: "root_moved" | "library_removed" | "library_added" | "path_not_local";
  library_id: number | null;
  library_name: string;
  manager_value: string | null;
  mediamop_value: string | null;
  detail: string;
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
  /** Ordered track sorters as JSON. Empty means the default order Refiner has always applied. */
  audio_sorters_json: string;
  subtitle_sorters_json: string;
  /** Keep the audio in the film's original language. Needs a metadata provider; without one the preferences decide. */
  keep_original_language: boolean;
  original_language_additional_csv: string;
  original_language_keep_only_first: boolean;
  original_language_first_if_none: boolean;
  original_language_treat_empty_as_original: boolean;
  /** An embedded poster is carried as a video stream, so this removes a stream as well as an image. */
  remove_images: boolean;
  remove_attachments: boolean;
  remove_title: boolean;
  remove_language_tags: boolean;
  remove_other_metadata: boolean;
  /** Libraries pointing at this rule set. Deleting one still in use is refused. */
  used_by_library_count: number;
  updated_at: string | null;
}

export type RefinerRuleSetWrite = Omit<
  RefinerRuleSet,
  "id" | "used_by_library_count" | "updated_at"
>;

/** Strip server-owned fields before a rule set is sent back to the API. */
export function writeFromRefinerRuleSet(
  value: RefinerRuleSet | RefinerRuleSetWrite,
): RefinerRuleSetWrite {
  return {
    name: value.name,
    primary_audio_lang: value.primary_audio_lang,
    secondary_audio_lang: value.secondary_audio_lang,
    tertiary_audio_lang: value.tertiary_audio_lang,
    default_audio_slot: value.default_audio_slot,
    remove_commentary: value.remove_commentary,
    subtitle_mode: value.subtitle_mode,
    subtitle_langs_csv: value.subtitle_langs_csv,
    preserve_forced_subs: value.preserve_forced_subs,
    preserve_default_subs: value.preserve_default_subs,
    audio_preference_mode: value.audio_preference_mode,
    audio_sorters_json: value.audio_sorters_json,
    subtitle_sorters_json: value.subtitle_sorters_json,
    keep_original_language: value.keep_original_language,
    original_language_additional_csv: value.original_language_additional_csv,
    original_language_keep_only_first: value.original_language_keep_only_first,
    original_language_first_if_none: value.original_language_first_if_none,
    original_language_treat_empty_as_original:
      value.original_language_treat_empty_as_original,
    remove_images: value.remove_images,
    remove_attachments: value.remove_attachments,
    remove_title: value.remove_title,
    remove_language_tags: value.remove_language_tags,
    remove_other_metadata: value.remove_other_metadata,
  };
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

export async function discoverRefinerLibraries(
  connectionId: number,
): Promise<DiscoverableRefinerLibrary[]> {
  const path = `${refinerLibrariesPath()}/discover/${connectionId}`;
  const response = await apiFetch(path);
  await requireOk(
    path,
    response,
    "Could not ask that media manager for its libraries",
  );
  return readJson<DiscoverableRefinerLibrary[]>(response);
}

export async function importDiscoveredRefinerLibraries(
  connectionId: number,
  keys: string[],
): Promise<RefinerLibrary[]> {
  const csrf_token = await fetchCsrfToken();
  const path = `${refinerLibrariesPath()}/discover/${connectionId}/import`;
  const response = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ keys, csrf_token }),
  });
  await requireOk(path, response, "Could not import those libraries");
  return readJson<RefinerLibrary[]>(response);
}

export async function fetchRefinerLibraryDrift(
  connectionId: number,
): Promise<RefinerLibraryDrift[]> {
  const path = `${refinerLibrariesPath()}/discover/${connectionId}/drift`;
  const response = await apiFetch(path);
  await requireOk(
    path,
    response,
    "Could not compare libraries with that media manager",
  );
  return readJson<RefinerLibraryDrift[]>(response);
}

export async function unlinkDiscoveredRefinerLibrary(
  id: number,
): Promise<RefinerLibrary> {
  const csrf_token = await fetchCsrfToken();
  const path = `${libraryPath(id)}/unlink`;
  const response = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token }),
  });
  await requireOk(path, response, "Could not unlink that library");
  return readJson<RefinerLibrary>(response);
}

export function writeFromRefinerLibrary(
  library: RefinerLibrary,
): RefinerLibraryWrite {
  return {
    name: library.name,
    media_scope: library.media_scope,
    enabled: library.enabled,
    watched_folder: library.watched_folder,
    work_folder: library.work_folder,
    output_folder: library.output_folder,
    media_extensions_csv: library.media_extensions_csv,
    exclude_markers_csv: library.exclude_markers_csv,
    include_patterns_csv: library.include_patterns_csv,
    exclude_patterns_csv: library.exclude_patterns_csv,
    min_file_size_mb: library.min_file_size_mb,
    max_file_size_mb: library.max_file_size_mb,
    rejected_file_action: library.rejected_file_action,
    min_file_age_seconds: library.min_file_age_seconds,
    created_after: library.created_after,
    created_before: library.created_before,
    modified_after: library.modified_after,
    modified_before: library.modified_before,
    exclude_hidden: library.exclude_hidden,
    top_level_only: library.top_level_only,
    scan_interval_seconds: library.scan_interval_seconds,
    hold_minutes: library.hold_minutes,
    sidecar_patterns_csv: library.sidecar_patterns_csv,
    preserve_original_timestamps: library.preserve_original_timestamps,
    output_collision_policy: library.output_collision_policy,
    hardware_decode_mode: library.hardware_decode_mode,
    hardware_device: library.hardware_device,
    hardware_disabled_vendors_csv: library.hardware_disabled_vendors_csv,
    ffmpeg_strictness: library.ffmpeg_strictness,
    file_detection_interval_seconds: library.file_detection_interval_seconds,
    ignore_size_changes: library.ignore_size_changes,
    skip_access_tests: library.skip_access_tests,
    file_system_events_enabled: library.file_system_events_enabled,
    max_attempts: library.max_attempts,
    retry_backoff_seconds: library.retry_backoff_seconds,
    retry_execution_failures: library.retry_execution_failures,
    retry_preflight_failures: library.retry_preflight_failures,
    schedule_grid: library.schedule_grid,
    schedule_enabled: library.schedule_enabled,
    schedule_hours_limited: library.schedule_hours_limited,
    schedule_days: library.schedule_days,
    schedule_start: library.schedule_start,
    schedule_end: library.schedule_end,
    max_concurrent_files: library.max_concurrent_files,
    priority: library.priority,
    rule_set_id: library.rule_set_id,
    manager_connection_ids: library.manager_connection_ids,
  };
}

const refinerRuleSetsPath = () => "/api/v1/refiner/rule-sets";

export async function fetchRefinerRuleSets(): Promise<RefinerRuleSet[]> {
  const path = refinerRuleSetsPath();
  const response = await apiFetch(path);
  await requireOk(path, response, "Could not load Refiner rule sets");
  return readJson<RefinerRuleSet[]>(response);
}

export async function createRefinerRuleSet(
  data: RefinerRuleSetWrite,
): Promise<RefinerRuleSet> {
  const csrf_token = await fetchCsrfToken();
  const path = refinerRuleSetsPath();
  const response = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...data, csrf_token }),
  });
  await requireOk(path, response, "Could not add that rule set");
  return readJson<RefinerRuleSet>(response);
}

export async function updateRefinerRuleSet(
  id: number,
  data: RefinerRuleSetWrite,
): Promise<RefinerRuleSet> {
  const csrf_token = await fetchCsrfToken();
  const path = `${refinerRuleSetsPath()}/${id}`;
  const response = await apiFetch(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...data, csrf_token }),
  });
  await requireOk(path, response, "Could not save that rule set");
  return readJson<RefinerRuleSet>(response);
}

export async function deleteRefinerRuleSet(id: number): Promise<void> {
  const csrf_token = await fetchCsrfToken();
  const path = `${refinerRuleSetsPath()}/${id}`;
  const response = await apiFetch(path, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token }),
  });
  await requireOk(path, response, "Could not remove that rule set");
}
