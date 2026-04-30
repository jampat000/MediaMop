import { describe, expect, it } from "vitest";
import { refinerJobsInspectionPath } from "./api";

describe("refinerJobsInspectionPath", () => {
  it("builds default recent listing URL", () => {
    expect(refinerJobsInspectionPath()).toBe(
      "/api/v1/refiner/jobs/inspection?limit=100",
    );
  });

  it("appends repeated status params", () => {
    const p = refinerJobsInspectionPath({
      limit: 10,
      statuses: ["pending", "leased"],
    });
    expect(p).toContain("/api/v1/refiner/jobs/inspection?");
    expect(p).toContain("limit=10");
    expect(p).toContain("status=pending");
    expect(p).toContain("status=leased");
  });
});
