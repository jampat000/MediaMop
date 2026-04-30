import { describe, expect, it } from "vitest";
import { refinerRuntimeSettingsPath } from "./runtime-settings-api";

describe("refinerRuntimeSettingsPath", () => {
  it("uses Refiner runtime-settings route", () => {
    expect(refinerRuntimeSettingsPath()).toBe(
      "/api/v1/refiner/runtime-settings",
    );
  });
});
