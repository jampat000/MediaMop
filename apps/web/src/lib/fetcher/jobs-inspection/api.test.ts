import { describe, expect, it } from "vitest";
import { fetcherJobsInspectionPath } from "./api";

describe("fetcherJobsInspectionPath", () => {
  it("builds the neutral Fetcher jobs inspection URL", () => {
    expect(fetcherJobsInspectionPath({ limit: 50 })).toBe("/api/v1/fetcher/jobs/inspection?limit=50");
    expect(fetcherJobsInspectionPath()).toBe("/api/v1/fetcher/jobs/inspection?limit=50");
  });

  it("appends repeated status params", () => {
    const p = fetcherJobsInspectionPath({ limit: 50, statuses: ["pending"] });
    expect(p).toContain("/api/v1/fetcher/jobs/inspection?");
    expect(p).toContain("limit=50");
    expect(p).toContain("status=pending");
  });
});
