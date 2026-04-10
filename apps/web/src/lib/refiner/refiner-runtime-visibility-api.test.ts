import { describe, expect, it } from "vitest";
import { refinerRuntimeVisibilityPath } from "./refiner-runtime-visibility-api";

describe("refinerRuntimeVisibilityPath", () => {
  it("returns the runtime visibility API path", () => {
    expect(refinerRuntimeVisibilityPath()).toBe("/api/v1/refiner/runtime/visibility");
  });
});
