/**
 * Library mode (#505): clean files already in a library, in place. Weir server (.NET) only — there is no
 * Python backend route to match (see apps/server/README.md, "Library mode").
 */
import { fetchCsrfToken } from "../api/auth-api";
import { apiFetch, readJson, requireOk } from "../api/client";
import { refinerStreamLanguageLabel } from "./stream-language-options";

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

/**
 * Issue #568: the facets the Library view breaks a library down by and filters its Files table on. Same names
 * the server stores and accepts, so a "show files" link is just this value in the query string.
 */
export const LIBRARY_FACETS = [
  "video_codec",
  "resolution",
  "audio",
  "audio_language",
  "subtitle_language",
] as const;

export type LibraryFacet = (typeof LIBRARY_FACETS)[number];

/** Why a file is not something Weir will clean (#568's Problems view). */
export type LibraryProblemKind =
  | "seeding"
  | "manager_redownload"
  | "no_permission"
  | "unreadable"
  | "no_video"
  | "no_audio_left";

/** The Files table's sortable columns, as the server names them. */
export const LIBRARY_FILE_SORTS = [
  "path",
  "title",
  "size",
  "state",
  "saved",
  "video",
  "resolution",
  "audio",
  "subtitles",
  "modified",
] as const;

export type LibraryFileSort = (typeof LIBRARY_FILE_SORTS)[number];

export interface LibraryFile {
  path: string;
  size_bytes: number;
  modified_at: number;
  classification: LibraryFileClassification;
  summary: string | null;
  reason: string | null;
  removed_audio_tracks: number;
  removed_subtitle_tracks: number;
  estimated_bytes_saved: number;
  manager_kind: string | null;
  manager_title: string | null;
  /** #568's media facts, from the ffprobe JSON the scan cached; "unknown" when it did not carry one. */
  video_codec: string;
  video_height: number | null;
  resolution_class: string;
  audio_track_count: number;
  subtitle_track_count: number;
  audio_summary: string | null;
  subtitle_summary: string | null;
  link_count: number | null;
  problem_kind: LibraryProblemKind | null;
}

export interface LibraryTotals {
  files: number;
  size_bytes: number;
  matches: number;
  would_change: number;
  cannot_process: number;
  total_removed_audio_tracks: number;
  total_removed_subtitle_tracks: number;
  estimated_bytes_saved: number;
}

export interface LibraryScanInfo {
  job_id: number | null;
  status: string;
  /** Queued or being worked on right now — what "Scan now" shows progress for. */
  running: boolean;
  generated_at: number | null;
  errors: string[];
}

export interface LibraryBreakdownRow {
  value: string;
  files: number;
  size_bytes: number;
  /** 0-1, computed on the server so every bar is drawn from one number. */
  share: number;
}

export type LibraryBreakdowns = Record<LibraryFacet, LibraryBreakdownRow[]>;

export interface LibraryProblemGroup {
  kind: LibraryProblemKind;
  title: string;
  what_to_do: string;
  files: number;
  size_bytes: number;
  sample_paths: string[];
}

export interface LibraryOverview {
  library_id: number;
  folders_configured: number;
  scan: LibraryScanInfo | null;
  totals: LibraryTotals;
  breakdowns: LibraryBreakdowns;
  problems: LibraryProblemGroup[];
}

export interface LibraryProblemsResult {
  library_id: number;
  scan: LibraryScanInfo | null;
  groups: LibraryProblemGroup[];
  total: number;
}

/** Every way the Files table can be narrowed, sorted and paged. */
export interface LibraryFileFilters {
  classification?: LibraryFileClassification;
  manager?: string;
  q?: string;
  problem?: LibraryProblemKind;
  facets?: Partial<Record<LibraryFacet, string>>;
  sort?: LibraryFileSort;
  direction?: "asc" | "desc";
  page?: number;
  page_size?: number;
}

export interface LibraryFilesResult {
  library_id: number;
  scan: LibraryScanInfo | null;
  /** The whole library, whatever the filters say — what the header reads. */
  summary: LibraryTotals;
  /** Just what the current filters select. */
  filtered: LibraryTotals;
  files: LibraryFile[];
  total: number;
  page: number;
  page_size: number;
  sort: LibraryFileSort;
  direction: "asc" | "desc";
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

/** Turns the Files table's filters into the query string the server reads them from. */
export function libraryFileFiltersToParams(
  filters: LibraryFileFilters,
): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.classification)
    params.set("classification", filters.classification);
  if (filters.manager) params.set("manager", filters.manager);
  if (filters.q) params.set("q", filters.q);
  if (filters.problem) params.set("problem", filters.problem);
  for (const facet of LIBRARY_FACETS) {
    const value = filters.facets?.[facet];
    if (value) params.set(facet, value);
  }
  if (filters.sort) params.set("sort", filters.sort);
  if (filters.direction) params.set("direction", filters.direction);
  if (filters.page && filters.page > 1)
    params.set("page", String(filters.page));
  if (filters.page_size) params.set("page_size", String(filters.page_size));
  return params;
}

export async function fetchLibraryFiles(
  libraryId: number,
  filters: LibraryFileFilters = {},
): Promise<LibraryFilesResult> {
  const suffix = libraryFileFiltersToParams(filters).toString();
  const path = `/api/v1/refiner/libraries/${libraryId}/library-files${suffix ? `?${suffix}` : ""}`;
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load this library's files");
  return readJson<LibraryFilesResult>(r);
}

/** #568's Overview: totals and every breakdown, aggregated on the server. */
export async function fetchLibraryOverview(
  libraryId: number,
): Promise<LibraryOverview> {
  const path = `/api/v1/refiner/libraries/${libraryId}/library-overview`;
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load this library's overview");
  return readJson<LibraryOverview>(r);
}

/** #568's Problems: files Weir will not clean, grouped by reason, each with what to do. */
export async function fetchLibraryProblems(
  libraryId: number,
): Promise<LibraryProblemsResult> {
  const path = `/api/v1/refiner/libraries/${libraryId}/library-problems`;
  const r = await apiFetch(path);
  await requireOk(path, r, "Could not load this library's problems");
  return readJson<LibraryProblemsResult>(r);
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

/** The heading each breakdown gets, and which sub-view shows it. */
export const LIBRARY_FACET_LABELS: Record<LibraryFacet, string> = {
  video_codec: "Video codec",
  resolution: "Resolution",
  audio: "Audio codec and channels",
  audio_language: "Audio languages",
  subtitle_language: "Subtitle languages",
};

/**
 * The server canonicalises a track language with `OriginalLanguage.CanonicalLanguage`, which picks the
 * ISO 639-2/B spelling ("ger", "fre", "chi"), while the operator picker lists the /T spelling ("deu",
 * "fra", "zho") for some of the same languages. Both name the same language, so a breakdown row would
 * otherwise read "ger" where the rest of the app says "German". Only the entries where the two standards
 * actually differ are listed.
 */
const LIBRARY_LANGUAGE_LABEL_ALIASES: Record<string, string> = {
  ger: "deu",
  chi: "zho",
  dut: "nld",
  cze: "ces",
  gre: "ell",
  rum: "ron",
  ice: "isl",
};

/** What one value of a facet reads as in the UI. Codes stay codes; only the display changes. */
export function libraryFacetValueLabel(
  facet: LibraryFacet,
  value: string,
): string {
  if (value === "unknown") return "Unknown";
  if (facet === "audio_language" || facet === "subtitle_language") {
    return refinerStreamLanguageLabel(
      LIBRARY_LANGUAGE_LABEL_ALIASES[value] ?? value,
    );
  }
  if (facet === "resolution") {
    return (
      { "4k": "4K", "1080p": "1080p", "720p": "720p", sd: "SD" }[value] ?? value
    );
  }
  if (facet === "audio") {
    const [codec, ...rest] = value.split(" ");
    return `${codec.toUpperCase()} ${rest.join(" ")}`.trim();
  }
  return value.toUpperCase();
}

/** A file's resolution as the Files table shows it, e.g. "4K" or "1080p". */
export function libraryResolutionLabel(resolutionClass: string): string {
  return libraryFacetValueLabel("resolution", resolutionClass);
}

/** A file's video codec as the Files table shows it; "Unknown" when the probe did not say. */
export function libraryCodecLabel(codec: string): string {
  return codec === "unknown" ? "Unknown" : codec.toUpperCase();
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
