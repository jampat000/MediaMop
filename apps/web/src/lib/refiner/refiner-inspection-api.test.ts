import { describe, expect, it } from "vitest";
import { refinerJobsInspectionPath } from "./refiner-inspection-api";

describe("refinerJobsInspectionPath", () => {
  it("includes only limit for terminal default (no status params)", () => {
    expect(refinerJobsInspectionPath({ limit: 50 })).toBe("/api/v1/refiner/jobs/inspection?limit=50");
    expect(refinerJobsInspectionPath()).toBe("/api/v1/refiner/jobs/inspection?limit=50");
  });

  it("appends repeated status for single-status filter", () => {
    const p = refinerJobsInspectionPath({ limit: 50, statuses: ["pending"] });
    expect(p).toContain("limit=50");
    expect(p).toContain("status=pending");
  });
});
