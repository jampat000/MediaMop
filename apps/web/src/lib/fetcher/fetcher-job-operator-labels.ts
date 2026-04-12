/**
 * Operator-facing labels for persisted ``fetcher_jobs`` rows (failed-import drives, Arr search, and any
 * future kinds). Keep string constants aligned with backend ``job_kind`` / dedupe contracts.
 */

export const FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE = "failed_import.radarr.cleanup_drive.v1" as const;
export const FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE = "failed_import.sonarr.cleanup_drive.v1" as const;

/** Arr search ``job_kind`` values (Fetcher lane). */
export const FETCHER_ARR_SEARCH_JOB_KIND_SONARR_MISSING = "missing_search.sonarr.monitored_episodes.v1" as const;
export const FETCHER_ARR_SEARCH_JOB_KIND_RADARR_MISSING = "missing_search.radarr.monitored_movies.v1" as const;
export const FETCHER_ARR_SEARCH_JOB_KIND_SONARR_UPGRADE = "upgrade_search.sonarr.cutoff_unmet.v1" as const;
export const FETCHER_ARR_SEARCH_JOB_KIND_RADARR_UPGRADE = "upgrade_search.radarr.cutoff_unmet.v1" as const;

/** Canonical failed-import cleanup drive ``job_kind`` values. */
export const FETCHER_FAILED_IMPORT_DRIVE_JOB_KINDS = [
  FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE,
  FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE,
] as const;

export type FetcherFailedImportDriveJobKind = (typeof FETCHER_FAILED_IMPORT_DRIVE_JOB_KINDS)[number];

const OPERATOR_LABEL_BY_FAILED_IMPORT_DRIVE_JOB_KIND = {
  [FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE]: "Radarr cleanup",
  [FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE]: "Sonarr cleanup",
} as const satisfies Record<FetcherFailedImportDriveJobKind, string>;

const OPERATOR_LABEL_BY_ARR_SEARCH_JOB_KIND: Record<string, string> = {
  [FETCHER_ARR_SEARCH_JOB_KIND_SONARR_MISSING]: "Sonarr missing search",
  [FETCHER_ARR_SEARCH_JOB_KIND_RADARR_MISSING]: "Radarr missing search",
  [FETCHER_ARR_SEARCH_JOB_KIND_SONARR_UPGRADE]: "Sonarr upgrade search",
  [FETCHER_ARR_SEARCH_JOB_KIND_RADARR_UPGRADE]: "Radarr upgrade search",
};

/** Dedupe keys for the long-lived failed-import drive rows (aligned with enqueue modules). */
export const FAILED_IMPORT_DRIVE_DEDUPE_KEY_RADARR = "failed_import.radarr.cleanup_drive:v1" as const;
export const FAILED_IMPORT_DRIVE_DEDUPE_KEY_SONARR = "failed_import.sonarr.cleanup_drive:v1" as const;

export const FETCHER_ARR_SEARCH_DEDUPE_SCHEDULED_SONARR_MISSING = "fetcher.search.scheduled:sonarr:missing:v1" as const;
export const FETCHER_ARR_SEARCH_DEDUPE_SCHEDULED_SONARR_UPGRADE = "fetcher.search.scheduled:sonarr:upgrade:v1" as const;
export const FETCHER_ARR_SEARCH_DEDUPE_SCHEDULED_RADARR_MISSING = "fetcher.search.scheduled:radarr:missing:v1" as const;
export const FETCHER_ARR_SEARCH_DEDUPE_SCHEDULED_RADARR_UPGRADE = "fetcher.search.scheduled:radarr:upgrade:v1" as const;

const OPERATOR_LABEL_BY_DRIVE_DEDUPE_KEY: Record<string, string> = {
  [FAILED_IMPORT_DRIVE_DEDUPE_KEY_RADARR]: OPERATOR_LABEL_BY_FAILED_IMPORT_DRIVE_JOB_KIND[
    FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE
  ],
  [FAILED_IMPORT_DRIVE_DEDUPE_KEY_SONARR]: OPERATOR_LABEL_BY_FAILED_IMPORT_DRIVE_JOB_KIND[
    FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE
  ],
  [FETCHER_ARR_SEARCH_DEDUPE_SCHEDULED_SONARR_MISSING]: OPERATOR_LABEL_BY_ARR_SEARCH_JOB_KIND[
    FETCHER_ARR_SEARCH_JOB_KIND_SONARR_MISSING
  ],
  [FETCHER_ARR_SEARCH_DEDUPE_SCHEDULED_SONARR_UPGRADE]: OPERATOR_LABEL_BY_ARR_SEARCH_JOB_KIND[
    FETCHER_ARR_SEARCH_JOB_KIND_SONARR_UPGRADE
  ],
  [FETCHER_ARR_SEARCH_DEDUPE_SCHEDULED_RADARR_MISSING]: OPERATOR_LABEL_BY_ARR_SEARCH_JOB_KIND[
    FETCHER_ARR_SEARCH_JOB_KIND_RADARR_MISSING
  ],
  [FETCHER_ARR_SEARCH_DEDUPE_SCHEDULED_RADARR_UPGRADE]: OPERATOR_LABEL_BY_ARR_SEARCH_JOB_KIND[
    FETCHER_ARR_SEARCH_JOB_KIND_RADARR_UPGRADE
  ],
};

export function fetcherJobKindOperatorLabel(jobKind: string): string {
  if (jobKind === FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE || jobKind === FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE) {
    return OPERATOR_LABEL_BY_FAILED_IMPORT_DRIVE_JOB_KIND[jobKind];
  }
  const arr = OPERATOR_LABEL_BY_ARR_SEARCH_JOB_KIND[jobKind];
  if (arr) {
    return arr;
  }
  return jobKind;
}

/**
 * Primary label for the stable dedupe column. Known production keys map to friendly labels;
 * otherwise fall back to the job-kind label so the default table view does not emphasize internal ids.
 */
export function fetcherJobDedupeKeyOperatorLabel(dedupeKey: string, jobKind: string): string {
  const mapped = OPERATOR_LABEL_BY_DRIVE_DEDUPE_KEY[dedupeKey];
  if (mapped) {
    return mapped;
  }
  return fetcherJobKindOperatorLabel(jobKind);
}
