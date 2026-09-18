import { fetchCsrfToken } from "../api/auth-api";
import { apiFetch, readJson, requireOk } from "../api/client";

export type ProcessingMediaType = "movie" | "tv";

export type ProcessingFailurePolicy = "pass_through" | "hold" | "reject";

export const PROCESSING_MEDIA_TYPE_LABELS: Record<ProcessingMediaType, string> =
  {
    movie: "Movies",
    tv: "TV episodes",
  };

/** One configured Processing library. Adding one is a POST, not a schema change. */
export interface ProcessingLibrary {
  id: number;
  name: string;
  enabled: boolean;
  media_type: ProcessingMediaType;
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
  /** What happens once retries run out: hand the original back, keep it, or reject the release (#465, #471). */
  failure_policy: ProcessingFailurePolicy;
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

export interface ProcessingLibraryWrite {
  name: string;
  media_type: ProcessingMediaType;
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
  /** What happens once retries run out: hand the original back, keep it, or reject the release (#465, #471). */
  failure_policy: ProcessingFailurePolicy;
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

/** A new library needs only a name and media type; the server fills in every other field's default. */
export type ProcessingLibraryCreate = Pick<
  ProcessingLibraryWrite,
  "name" | "media_type"
> &
  Partial<ProcessingLibraryWrite>;

export interface DiscoverableProcessingLibrary {
  key: string;
  name: string;
  media_type: ProcessingMediaType | null;
  root_path: string | null;
  already_imported: boolean;
  local_path_problem: string | null;
  processes_before_import: boolean;
  output_path: string | null;
  output_path_problem: string | null;
}

export interface ProcessingLibraryDrift {
  kind: "root_moved" | "library_removed" | "library_added" | "path_not_local";
  library_id: number | null;
  library_name: string;
  manager_value: string | null;
  weir_value: string | null;
  detail: string;
}

/** Issue #498: per-flag track name templates, checked forced, then hearing-impaired, then commentary, then audio description. */
export interface ProcessingTrackNameOverrides {
  forced: string;
  hearing_impaired: string;
  commentary: string;
  audio_description: string;
}

export interface ProcessingRuleSet {
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
  /** Ordered track sorters as JSON. Empty means the default order Processing has always applied. */
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
  /** Issue #495: drop a subtitle track detected as hearing-impaired (SDH/CC), from its flag or its name. Off by default. */
  remove_hearing_impaired_subs: boolean;
  /** Issue #497: "single" (today's behaviour) or "per_language" — keep the best track of each configured audio language. */
  audio_keep_mode: string;
  /** Issue #497: 0 (default) means unlimited; otherwise the most subtitle tracks kept per language. */
  subtitle_max_per_language: number;
  /** Issue #497: "text_first" (default), "image_first" or "accessibility" — how the subtitle cap picks a winner. */
  subtitle_quality_strategy: string;
  /** Issue #498: write a standard name on every kept audio/subtitle track, from a template. Off by default. */
  standardize_track_names: boolean;
  /** Issue #498: placeholders {language} {variant} {channels} {codec} {flags}. */
  track_name_template: string;
  track_name_overrides: ProcessingTrackNameOverrides;
  /** Issue #498: clear scene-tag video track names (e.g. "x265-GROUP"). Off by default. */
  clear_video_track_names: boolean;
  /** Issue #498: drop the container's chapter list. Off by default. */
  remove_chapters: boolean;
  /** Libraries pointing at this rule set. Deleting one still in use is refused. */
  used_by_library_count: number;
  updated_at: string | null;
}

export type ProcessingRuleSetWrite = Omit<
  ProcessingRuleSet,
  "id" | "used_by_library_count" | "updated_at"
>;

/** Strip server-owned fields before a rule set is sent back to the API. */
export function writeFromProcessingRuleSet(
  value: ProcessingRuleSet | ProcessingRuleSetWrite,
): ProcessingRuleSetWrite {
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
    remove_hearing_impaired_subs: value.remove_hearing_impaired_subs,
    audio_keep_mode: value.audio_keep_mode,
    subtitle_max_per_language: value.subtitle_max_per_language,
    subtitle_quality_strategy: value.subtitle_quality_strategy,
    standardize_track_names: value.standardize_track_names,
    track_name_template: value.track_name_template,
    track_name_overrides: { ...value.track_name_overrides },
    clear_video_track_names: value.clear_video_track_names,
    remove_chapters: value.remove_chapters,
  };
}

export const processingLibrariesPath = () => "/api/v1/processing/libraries";
const libraryPath = (id: number) => `${processingLibrariesPath()}/${id}`;

export async function fetchProcessingLibraries(): Promise<ProcessingLibrary[]> {
  const path = processingLibrariesPath();
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load libraries");
  return readJson<ProcessingLibrary[]>(r);
}

export async function createProcessingLibrary(
  data: ProcessingLibraryCreate,
): Promise<ProcessingLibrary> {
  const csrf_token = await fetchCsrfToken();
  const path = processingLibrariesPath();
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...data, csrf_token }),
  });
  await requireOk(path, r, "Could not add that library");
  return readJson<ProcessingLibrary>(r);
}

export async function updateProcessingLibrary(
  id: number,
  data: ProcessingLibraryWrite,
): Promise<ProcessingLibrary> {
  const csrf_token = await fetchCsrfToken();
  const path = libraryPath(id);
  const r = await apiFetch(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...data, csrf_token }),
  });
  await requireOk(path, r, "Could not save that library");
  return readJson<ProcessingLibrary>(r);
}

export async function deleteProcessingLibrary(id: number): Promise<void> {
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

export async function reorderProcessingLibraries(
  library_ids_in_order: number[],
): Promise<ProcessingLibrary[]> {
  const csrf_token = await fetchCsrfToken();
  const path = `${processingLibrariesPath()}/reorder`;
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ library_ids_in_order, csrf_token }),
  });
  await requireOk(path, r, "Could not reorder libraries");
  return readJson<ProcessingLibrary[]>(r);
}

export async function discoverProcessingLibraries(
  connectionId: number,
): Promise<DiscoverableProcessingLibrary[]> {
  const path = `${processingLibrariesPath()}/discover/${connectionId}`;
  const response = await apiFetch(path);
  await requireOk(
    path,
    response,
    "Could not ask that media manager for its libraries",
  );
  return readJson<DiscoverableProcessingLibrary[]>(response);
}

export async function importDiscoveredProcessingLibraries(
  connectionId: number,
  keys: string[],
): Promise<ProcessingLibrary[]> {
  const csrf_token = await fetchCsrfToken();
  const path = `${processingLibrariesPath()}/discover/${connectionId}/import`;
  const response = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ keys, csrf_token }),
  });
  await requireOk(path, response, "Could not import those libraries");
  return readJson<ProcessingLibrary[]>(response);
}

export async function fetchProcessingLibraryDrift(
  connectionId: number,
): Promise<ProcessingLibraryDrift[]> {
  const path = `${processingLibrariesPath()}/discover/${connectionId}/drift`;
  const response = await apiFetch(path);
  await requireOk(
    path,
    response,
    "Could not compare libraries with that media manager",
  );
  return readJson<ProcessingLibraryDrift[]>(response);
}

export async function unlinkDiscoveredProcessingLibrary(
  id: number,
): Promise<ProcessingLibrary> {
  const csrf_token = await fetchCsrfToken();
  const path = `${libraryPath(id)}/unlink`;
  const response = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token }),
  });
  await requireOk(path, response, "Could not unlink that library");
  return readJson<ProcessingLibrary>(response);
}

export function writeFromProcessingLibrary(
  library: ProcessingLibrary,
): ProcessingLibraryWrite {
  return {
    name: library.name,
    media_type: library.media_type,
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
    failure_policy: library.failure_policy,
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

/** Whether Reject can be chosen for a library linked to these managers, and why. */
export interface ProcessingRejectSupport {
  available: boolean;
  reason: string;
}

export async function fetchProcessingRejectSupport(
  connectionIds: number[],
): Promise<ProcessingRejectSupport> {
  const query = new URLSearchParams();
  for (const id of connectionIds) query.append("connection_ids", String(id));
  const suffix = query.toString();
  const path = `/api/v1/processing/reject-support${suffix ? `?${suffix}` : ""}`;
  const response = await apiFetch(path);
  await requireOk(
    path,
    response,
    "Could not check whether Reject is available",
  );
  return readJson<ProcessingRejectSupport>(response);
}

const processingRuleSetsPath = () => "/api/v1/processing/rule-sets";

export async function fetchProcessingRuleSets(): Promise<ProcessingRuleSet[]> {
  const path = processingRuleSetsPath();
  const response = await apiFetch(path);
  await requireOk(path, response, "Could not load rule sets");
  return readJson<ProcessingRuleSet[]>(response);
}

export async function createProcessingRuleSet(
  data: ProcessingRuleSetWrite,
): Promise<ProcessingRuleSet> {
  const csrf_token = await fetchCsrfToken();
  const path = processingRuleSetsPath();
  const response = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...data, csrf_token }),
  });
  await requireOk(path, response, "Could not add that rule set");
  return readJson<ProcessingRuleSet>(response);
}

export async function updateProcessingRuleSet(
  id: number,
  data: ProcessingRuleSetWrite,
): Promise<ProcessingRuleSet> {
  const csrf_token = await fetchCsrfToken();
  const path = `${processingRuleSetsPath()}/${id}`;
  const response = await apiFetch(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...data, csrf_token }),
  });
  await requireOk(path, response, "Could not save that rule set");
  return readJson<ProcessingRuleSet>(response);
}

export async function deleteProcessingRuleSet(id: number): Promise<void> {
  const csrf_token = await fetchCsrfToken();
  const path = `${processingRuleSetsPath()}/${id}`;
  const response = await apiFetch(path, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token }),
  });
  await requireOk(path, response, "Could not remove that rule set");
}

/**
 * The type badge beside a library's name, or null when the name already says it
 * ("Movies · Movies"). Shared by every page that lists libraries so they agree on
 * when the badge is worth the room.
 */
export function processingMediaTypeBadge(
  library: Pick<ProcessingLibrary, "name" | "media_type">,
): string | null {
  const label = PROCESSING_MEDIA_TYPE_LABELS[library.media_type];
  const name = library.name.trim().toLowerCase();
  const lower = label.toLowerCase();
  if (!name || lower.includes(name) || name.includes(lower)) return null;
  if (library.media_type === "tv" && /\b(tv|shows?|series)\b/.test(name)) {
    return null;
  }
  return label;
}
