import { describe, expect, it } from "vitest";
import { refinerRuntimeVisibilityPath } from "./refiner-runtime-visibility-api";

describe("refinerRuntimeVisibilityPath", () => {
  it("points at the Pass 22 visibility route", () => {
    expect(refinerRuntimeVisibilityPath()).toBe("/api/v1/refiner/runtime/visibility");
  });
});
