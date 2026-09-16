import { describe, expect, it } from "vitest";
import { activityExportPath, activityRecentPath } from "./activity-api";

describe("activity-api paths", () => {
  it("sends the new history filters on the feed", () => {
    const path = activityRecentPath({
      limit: 100,
      trigger: "scheduled",
      result: "failed",
      library_id: 3,
      file: "Movies/A b.mkv",
      before_id: 9,
    });
    const url = new URL(path, "http://x");
    expect(url.pathname).toBe("/api/v1/activity/recent");
    expect(url.searchParams.get("trigger")).toBe("scheduled");
    expect(url.searchParams.get("result")).toBe("failed");
    expect(url.searchParams.get("library_id")).toBe("3");
    expect(url.searchParams.get("file")).toBe("Movies/A b.mkv");
    expect(url.searchParams.get("before_id")).toBe("9");
    expect(url.searchParams.get("limit")).toBe("100");
  });

  it("exports the same filters without paging", () => {
    const path = activityExportPath("json", {
      limit: 100,
      before_id: 9,
      module: "refiner",
      trigger: "webhook",
      date_from: "2026-09-16T08:00:00.000Z",
    });
    const url = new URL(path, "http://x");
    expect(url.pathname).toBe("/api/v1/activity/export");
    expect(url.searchParams.get("format")).toBe("json");
    expect(url.searchParams.get("module")).toBe("refiner");
    expect(url.searchParams.get("trigger")).toBe("webhook");
    expect(url.searchParams.get("date_from")).toBe("2026-09-16T08:00:00.000Z");
    expect(url.searchParams.has("limit")).toBe(false);
    expect(url.searchParams.has("before_id")).toBe(false);
  });
});
