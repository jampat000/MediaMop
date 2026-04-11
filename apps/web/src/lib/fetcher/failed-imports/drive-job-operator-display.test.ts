import { describe, expect, it } from "vitest";
import {
  FAILED_IMPORT_DRIVE_DEDUPE_KEY_RADARR,
  FAILED_IMPORT_DRIVE_DEDUPE_KEY_SONARR,
  FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE,
  FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE,
  FETCHER_FAILED_IMPORT_DRIVE_JOB_KINDS,
  failedImportDriveJobKindOperatorLabel,
  failedImportDriveStableKeyOperatorLabel,
} from "./drive-job-operator-display";

describe("failedImportDriveJobKindOperatorLabel", () => {
  it("maps known drive job kinds to operator labels", () => {
    expect(failedImportDriveJobKindOperatorLabel(FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE)).toBe("Radarr cleanup");
    expect(failedImportDriveJobKindOperatorLabel(FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE)).toBe("Sonarr cleanup");
  });

  it("falls back to the raw kind for unknown values", () => {
    expect(failedImportDriveJobKindOperatorLabel("unknown.kind.v1")).toBe("unknown.kind.v1");
  });
});

describe("FETCHER_FAILED_IMPORT_DRIVE_JOB_KINDS", () => {
  it("has a non-empty operator label for every canonical drive kind", () => {
    for (const kind of FETCHER_FAILED_IMPORT_DRIVE_JOB_KINDS) {
      const label = failedImportDriveJobKindOperatorLabel(kind);
      expect(label.length).toBeGreaterThan(0);
      expect(label).not.toBe(kind);
    }
  });
});

describe("failedImportDriveStableKeyOperatorLabel", () => {
  it("maps canonical dedupe keys without surfacing raw internal strings as the primary label", () => {
    expect(failedImportDriveStableKeyOperatorLabel(FAILED_IMPORT_DRIVE_DEDUPE_KEY_RADARR, "ignored")).toBe(
      "Radarr cleanup",
    );
    expect(failedImportDriveStableKeyOperatorLabel(FAILED_IMPORT_DRIVE_DEDUPE_KEY_SONARR, "ignored")).toBe(
      "Sonarr cleanup",
    );
  });

  it("falls back to the job-kind label when the dedupe key is unknown", () => {
    expect(failedImportDriveStableKeyOperatorLabel("insp-pending", "k.manual")).toBe("k.manual");
  });
});
