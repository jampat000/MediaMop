import { describe, expect, it } from "vitest";
import { processingJobsInspectionPath } from "./api";

describe("processingJobsInspectionPath", () => {
  it("builds default recent listing URL", () => {
    expect(processingJobsInspectionPath()).toBe(
      "/api/v1/processing/jobs/inspection?limit=100",
    );
  });

  it("appends repeated status params", () => {
    const p = processingJobsInspectionPath({
      limit: 10,
      statuses: ["pending", "leased"],
    });
    expect(p).toContain("/api/v1/processing/jobs/inspection?");
    expect(p).toContain("limit=10");
    expect(p).toContain("status=pending");
    expect(p).toContain("status=leased");
  });
});
