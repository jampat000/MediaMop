import { describe, expect, it } from "vitest";
import { prunerApplyEligibilityPath, prunerPreviewRunsListPath } from "./api";

describe("prunerApplyEligibilityPath", () => {
  it("scopes apply eligibility under instance + media_scope + preview id", () => {
    expect(prunerApplyEligibilityPath(5, "movies", "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")).toBe(
      "/api/v1/pruner/instances/5/scopes/movies/preview-runs/aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee/apply-eligibility",
    );
  });
});

describe("prunerPreviewRunsListPath", () => {
  it("builds the list URL and optional query string", () => {
    expect(prunerPreviewRunsListPath(12)).toBe("/api/v1/pruner/instances/12/preview-runs");
    const q = prunerPreviewRunsListPath(3, { media_scope: "tv", limit: 7 });
    expect(q).toContain("/api/v1/pruner/instances/3/preview-runs?");
    expect(q).toContain("media_scope=tv");
    expect(q).toContain("limit=7");
  });
});
