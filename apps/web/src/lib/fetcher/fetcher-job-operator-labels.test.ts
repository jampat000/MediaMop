import { describe, expect, it } from "vitest";
import {
  FAILED_IMPORT_DRIVE_DEDUPE_KEY_RADARR,
  FAILED_IMPORT_DRIVE_DEDUPE_KEY_SONARR,
  FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE,
  FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE,
  FETCHER_ARR_SEARCH_DEDUPE_SCHEDULED_RADARR_MISSING,
  FETCHER_ARR_SEARCH_DEDUPE_SCHEDULED_SONARR_UPGRADE,
  FETCHER_ARR_SEARCH_JOB_KIND_RADARR_MISSING,
  FETCHER_ARR_SEARCH_JOB_KIND_SONARR_UPGRADE,
  FETCHER_FAILED_IMPORT_DRIVE_JOB_KINDS,
  fetcherJobDedupeKeyOperatorLabel,
  fetcherJobKindOperatorLabel,
} from "./fetcher-job-operator-labels";

describe("fetcherJobKindOperatorLabel", () => {
  it("maps known drive job kinds to operator labels", () => {
    expect(fetcherJobKindOperatorLabel(FAILED_IMPORT_JOB_KIND_RADARR_CLEANUP_DRIVE)).toBe("Radarr cleanup");
    expect(fetcherJobKindOperatorLabel(FAILED_IMPORT_JOB_KIND_SONARR_CLEANUP_DRIVE)).toBe("Sonarr cleanup");
  });

  it("falls back to the raw kind for unknown values", () => {
    expect(fetcherJobKindOperatorLabel("unknown.kind.v1")).toBe("unknown.kind.v1");
  });

  it("maps Arr search job kinds to operator labels", () => {
    expect(fetcherJobKindOperatorLabel(FETCHER_ARR_SEARCH_JOB_KIND_SONARR_UPGRADE)).toBe("Sonarr upgrade search");
    expect(fetcherJobKindOperatorLabel(FETCHER_ARR_SEARCH_JOB_KIND_RADARR_MISSING)).toBe("Radarr missing search");
  });
});

describe("FETCHER_FAILED_IMPORT_DRIVE_JOB_KINDS", () => {
  it("has a non-empty operator label for every canonical drive kind", () => {
    for (const kind of FETCHER_FAILED_IMPORT_DRIVE_JOB_KINDS) {
      const label = fetcherJobKindOperatorLabel(kind);
      expect(label.length).toBeGreaterThan(0);
      expect(label).not.toBe(kind);
    }
  });
});

describe("fetcherJobDedupeKeyOperatorLabel", () => {
  it("maps canonical dedupe keys without surfacing raw internal strings as the primary label", () => {
    expect(fetcherJobDedupeKeyOperatorLabel(FAILED_IMPORT_DRIVE_DEDUPE_KEY_RADARR, "ignored")).toBe("Radarr cleanup");
    expect(fetcherJobDedupeKeyOperatorLabel(FAILED_IMPORT_DRIVE_DEDUPE_KEY_SONARR, "ignored")).toBe("Sonarr cleanup");
  });

  it("falls back to the job-kind label when the dedupe key is unknown", () => {
    expect(fetcherJobDedupeKeyOperatorLabel("insp-pending", "k.manual")).toBe("k.manual");
  });

  it("maps scheduled Arr search dedupe keys to operator labels", () => {
    expect(fetcherJobDedupeKeyOperatorLabel(FETCHER_ARR_SEARCH_DEDUPE_SCHEDULED_RADARR_MISSING, "ignored")).toBe(
      "Radarr missing search",
    );
    expect(fetcherJobDedupeKeyOperatorLabel(FETCHER_ARR_SEARCH_DEDUPE_SCHEDULED_SONARR_UPGRADE, "ignored")).toBe(
      "Sonarr upgrade search",
    );
  });
});
