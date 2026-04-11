/**
 * Operator-facing copy for failed-import drive inspection (must stay aligned with
 * ``mediamop.modules.fetcher.failed_import_drive_job_kinds`` on the backend).
 */

export const FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE = "failed_import.radarr.cleanup_drive.v1" as const;
export const FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE = "failed_import.sonarr.cleanup_drive.v1" as const;

/** Canonical drive ``job_kind`` values surfaced on the Fetcher failed-imports page. */
export const FETCHER_FAILED_IMPORT_DRIVE_JOB_KINDS = [
  FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE,
  FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE,
] as const;

export type FetcherFailedImportDriveJobKind = (typeof FETCHER_FAILED_IMPORT_DRIVE_JOB_KINDS)[number];

const OPERATOR_LABEL_BY_FAILED_IMPORT_DRIVE_JOB_KIND = {
  [FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE]: "Radarr cleanup",
  [FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE]: "Sonarr cleanup",
} as const satisfies Record<FetcherFailedImportDriveJobKind, string>;

/** Dedupe keys for the long-lived drive rows (aligned with enqueue modules). */
export const FAILED_IMPORT_DRIVE_DEDUPE_KEY_RADARR = "failed_import.radarr.cleanup_drive:v1" as const;
export const FAILED_IMPORT_DRIVE_DEDUPE_KEY_SONARR = "failed_import.sonarr.cleanup_drive:v1" as const;

const OPERATOR_LABEL_BY_DRIVE_DEDUPE_KEY: Record<string, string> = {
  [FAILED_IMPORT_DRIVE_DEDUPE_KEY_RADARR]: OPERATOR_LABEL_BY_FAILED_IMPORT_DRIVE_JOB_KIND[
    FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE
  ],
  [FAILED_IMPORT_DRIVE_DEDUPE_KEY_SONARR]: OPERATOR_LABEL_BY_FAILED_IMPORT_DRIVE_JOB_KIND[
    FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE
  ],
};

export function failedImportDriveJobKindOperatorLabel(jobKind: string): string {
  if (jobKind === FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE || jobKind === FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE) {
    return OPERATOR_LABEL_BY_FAILED_IMPORT_DRIVE_JOB_KIND[jobKind];
  }
  return jobKind;
}

/**
 * Primary label for the stable dedupe column. Known production keys map to the same
 * operator labels as drive job kinds; otherwise fall back to the work-type label so
 * the default table view does not emphasize internal identifiers.
 */
export function failedImportDriveStableKeyOperatorLabel(dedupeKey: string, jobKind: string): string {
  const mapped = OPERATOR_LABEL_BY_DRIVE_DEDUPE_KEY[dedupeKey];
  if (mapped) {
    return mapped;
  }
  return failedImportDriveJobKindOperatorLabel(jobKind);
}
