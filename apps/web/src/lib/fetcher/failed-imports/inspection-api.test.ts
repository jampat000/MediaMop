import { describe, expect, it } from "vitest";
import { failedImportTasksInspectionPath } from "./inspection-api";

describe("failedImportTasksInspectionPath", () => {
  it("targets Fetcher failed-imports inspection under /api/v1", () => {
    expect(failedImportTasksInspectionPath({ limit: 50 })).toBe(
      "/api/v1/fetcher/failed-imports/inspection?limit=50",
    );
    expect(failedImportTasksInspectionPath()).toBe("/api/v1/fetcher/failed-imports/inspection?limit=50");
  });

  it("repeats status query params when filtering", () => {
    const p = failedImportTasksInspectionPath({ limit: 50, statuses: ["pending"] });
    expect(p).toContain("/api/v1/fetcher/failed-imports/inspection?");
    expect(p).toContain("limit=50");
    expect(p).toContain("status=pending");
  });
});
