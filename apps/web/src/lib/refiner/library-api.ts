/**
 * Library mode (#505): clean files already in a library, in place. Weir server (.NET) only — there is no
 * Python backend route to match (see apps/server/README.md, "Library mode").
 */
import { fetchCsrfToken } from "../api/auth-api";
import { apiFetch, readJson, requireOk } from "../api/client";

export type LibraryFileClassification =
  "matches" | "would_change" | "cannot_process";

export const LIBRARY_FILE_CLASSIFICATION_LABELS: Record<
  LibraryFileClassification,
  string
> = {
  matches: "Matches the rules",
  would_change: "Would change",
  cannot_process: "Cannot process",
};

/**
 * Issue #551: the manager kinds a library file can be matched to (only Sonarr/Radarr support the title
 * listing the match is built from — see apps/server/README.md's "Manager title matching"), for the Library
 * tab's manager filter. Matches the `manager` query param `fetchLibraryFiles` already sends straight through
 * to `manager_kind` on the server.
 */
export const LIBRARY_MANAGER_FILTER_OPTIONS: {
  value: string;
  label: string;
}[] = [
  { value: "radarr", label: "Radarr" },
  { value: "sonarr", label: "Sonarr" },
];

export interface LibrarySettings {
  library_folders: string[];
  library_schedule_enabled: boolean;
  /** #508 step 1: clean a file even while another name still shares its data (seeding). Default false. */
  clean_hardlinked_files: boolean;
  /** #508 step 2: skip a clean that would make a manager re-download the title. Default true. Not yet enforced
   * server-side — see apps/server/README.md's "Seams for #507, #508 and #509" — but always safe to save. */
  skip_if_manager_would_redownload: boolean;
}

export interface LibraryFile {
  path: string;
  size_bytes: number;
  classification: LibraryFileClassification;
  summary: string | null;
  reason: string | null;
  removed_audio_tracks: number;
  removed_subtitle_tracks: number;
  estimated_bytes_saved: number;
  manager_kind: string | null;
  manager_title: string | null;
}

export interface LibraryFilesSummary {
  matches: number;
  would_change: number;
  cannot_process: number;
  total_removed_audio_tracks: number;
  total_removed_subtitle_tracks: number;
  estimated_bytes_saved: number;
}

export interface LibraryScanInfo {
  job_id: number;
  status: string;
  generated_at: number | null;
}

export interface LibraryFilesResult {
  library_id: number;
  scan: LibraryScanInfo | null;
  summary: LibraryFilesSummary;
  files: LibraryFile[];
  total: number;
}

export interface LibraryScanTrigger {
  job_id: number;
  status: string;
  already_running: boolean;
}

/** The exact #505 point 5 confirmation: "N files, M tracks will be removed..." plus the size behind it. */
export interface LibraryConfirmationRequired {
  kind: "confirmation_required";
  detail: string;
  files_count: number;
  tracks_count: number;
  estimated_bytes_saved: number;
  /** #508's per-file preflight notes (seeding, re-download risk), one line per file that would be skipped. */
  warnings?: string[];
}

export interface LibraryCleanResult {
  kind: "cleaned";
  queued: number;
  job_ids: number[];
  files_count: number;
  tracks_count: number;
  estimated_bytes_saved: number;
  /** #508: paths selected for cleaning but skipped outright (still shared with a download). */
  skipped_paths: string[];
  /** #508's per-file preflight notes, same shape as the confirmation dialog's. */
  warnings: string[];
}

function librarySettingsPath(libraryId: number): string {
  return `/api/v1/refiner/libraries/${libraryId}/library-settings`;
}

export async function fetchLibrarySettings(
  libraryId: number,
): Promise<LibrarySettings> {
  const path = librarySettingsPath(libraryId);
  const r = await apiFetch(path);
  await requireOk(
    path,
    r,
    "Could not load this library's library-mode settings",
  );
  return readJson<LibrarySettings>(r);
}

export async function saveLibraryFolders(
  libraryId: number,
  library_folders: string[],
): Promise<LibrarySettings> {
  return saveLibrarySettings(libraryId, { library_folders });
}

/**
 * PUTs library-mode settings. `library_folders` is required on every call (the API replaces the whole list, not
 * just the fields sent, when it is present — an absent list is read as "no folders", not "leave unchanged"), so a
 * checkbox-only save must still pass the library's current folders. `clean_hardlinked_files` and
 * `skip_if_manager_would_redownload` are each optional and keep their saved value when left out.
 */
export async function saveLibrarySettings(
  libraryId: number,
  updates: {
    library_folders: string[];
    clean_hardlinked_files?: boolean;
    skip_if_manager_would_redownload?: boolean;
  },
): Promise<LibrarySettings> {
  const csrf_token = await fetchCsrfToken();
  const path = librarySettingsPath(libraryId);
  const r = await apiFetch(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...updates, csrf_token }),
  });
  await requireOk(path, r, "Could not save this library's settings");
  return readJson<LibrarySettings>(r);
}

export async function triggerLibraryScan(
  libraryId: number,
): Promise<LibraryScanTrigger> {
  const csrf_token = await fetchCsrfToken();
  const path = `/api/v1/refiner/libraries/${libraryId}/library-scan`;
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csrf_token }),
  });
  await requireOk(path, r, "Could not start a library scan");
  return readJson<LibraryScanTrigger>(r);
}

export async function fetchLibraryFiles(
  libraryId: number,
  filters: {
    classification?: LibraryFileClassification;
    manager?: string;
    q?: string;
  } = {},
): Promise<LibraryFilesResult> {
  const params = new URLSearchParams();
  if (filters.classification)
    params.set("classification", filters.classification);
  if (filters.manager) params.set("manager", filters.manager);
  if (filters.q) params.set("q", filters.q);
  const suffix = params.toString();
  const path = `/api/v1/refiner/libraries/${libraryId}/library-files${suffix ? `?${suffix}` : ""}`;
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load this library's files");
  return readJson<LibraryFilesResult>(r);
}

/** Parses the structured 400 the API returns when removal needs confirming. Rethrows anything else. */
async function readConfirmationOr<T>(
  path: string,
  r: Response,
  fallback: string,
): Promise<LibraryConfirmationRequired | T> {
  if (r.status === 400) {
    const body = await readJson<Record<string, unknown>>(r);
    if (body && body.error === "confirm_final_removal_required") {
      return {
        kind: "confirmation_required",
        detail: String(body.detail ?? ""),
        files_count: Number(body.files_count ?? 0),
        tracks_count: Number(body.tracks_count ?? 0),
        estimated_bytes_saved: Number(body.estimated_bytes_saved ?? 0),
        warnings: Array.isArray(body.warnings)
          ? body.warnings.map(String)
          : undefined,
      };
    }
  }
  await requireOk(path, r, fallback);
  return readJson<T>(r);
}

export async function cleanLibraryFiles(
  libraryId: number,
  paths: string[],
  confirm_final_removal: boolean,
): Promise<LibraryConfirmationRequired | LibraryCleanResult> {
  const csrf_token = await fetchCsrfToken();
  const path = `/api/v1/refiner/libraries/${libraryId}/library-files/clean`;
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paths, confirm_final_removal, csrf_token }),
  });
  const result = await readConfirmationOr<Omit<LibraryCleanResult, "kind">>(
    path,
    r,
    "Could not queue those files to clean",
  );
  return "kind" in result ? result : { kind: "cleaned", ...result };
}

export async function setLibrarySchedule(
  libraryId: number,
  enabled: boolean,
  confirm_final_removal: boolean,
): Promise<LibraryConfirmationRequired | LibrarySettings> {
  const csrf_token = await fetchCsrfToken();
  const path = `/api/v1/refiner/libraries/${libraryId}/library-schedule`;
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled, confirm_final_removal, csrf_token }),
  });
  return readConfirmationOr<LibrarySettings>(
    path,
    r,
    "Could not change the library schedule",
  );
}

/** One track a Refiner pass removed from a file for good (issue #509). */
export interface RemovedTrack {
  language: string;
  type: "audio" | "subtitle";
  codec: string;
  variant: string | null;
  reason: string;
}

/**
 * One title whose current rules would now keep a track a past clean removed for good (#509 step 2). The
 * "Download again" action is only ever shown when `can_redownload` is true: a manager kind #509 verified
 * (Sonarr/Radarr) and a file #551's title matching actually resolved to one of that manager's titles.
 * `unavailable_reason` explains why in plain language when it is false.
 */
export interface LibraryRedownloadTitle {
  path: string;
  manager_kind: string | null;
  manager_title: string | null;
  removed_tracks: RemovedTrack[];
  can_redownload: boolean;
  confirmation_message: string | null;
  unavailable_reason: string | null;
}

export interface LibraryRedownloadsResult {
  library_id: number;
  titles: LibraryRedownloadTitle[];
  total: number;
}

export interface LibraryRedownloadResult {
  path: string;
  outcome: string;
  message: string;
}

export async function fetchLibraryRedownloads(
  libraryId: number,
): Promise<LibraryRedownloadsResult> {
  const path = `/api/v1/refiner/libraries/${libraryId}/library-redownloads`;
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load titles missing tracks");
  return readJson<LibraryRedownloadsResult>(r);
}

export async function requestLibraryRedownload(
  libraryId: number,
  filePath: string,
): Promise<LibraryRedownloadResult> {
  const csrf_token = await fetchCsrfToken();
  const path = `/api/v1/refiner/libraries/${libraryId}/library-redownloads`;
  const r = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      path: filePath,
      confirm_destructive: true,
      csrf_token,
    }),
  });
  await requireOk(path, r, "Could not ask the manager to download this again");
  return readJson<LibraryRedownloadResult>(r);
}

/** Bytes as an operator reads them: binary units, one decimal from KB up (mirrors SafeSwapRules.FormatBytes). */
export function formatBytes(bytes: number): string {
  const units = ["bytes", "KB", "MB", "GB", "TB"];
  let value = Math.max(0, bytes);
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return unit === 0
    ? `${Math.trunc(value)} bytes`
    : `${value.toFixed(1)} ${units[unit]}`;
}
