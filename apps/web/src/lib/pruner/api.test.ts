import { describe, expect, it } from "vitest";
import { prunerPreviewRunsListPath } from "./api";

describe("prunerPreviewRunsListPath", () => {
  it("builds the list URL and optional query string", () => {
    expect(prunerPreviewRunsListPath(12)).toBe("/api/v1/pruner/instances/12/preview-runs");
    const q = prunerPreviewRunsListPath(3, { media_scope: "tv", limit: 7 });
    expect(q).toContain("/api/v1/pruner/instances/3/preview-runs?");
    expect(q).toContain("media_scope=tv");
    expect(q).toContain("limit=7");
  });
});
