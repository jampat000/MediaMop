import { describe, expect, it } from "vitest";
import { processingRuntimeSettingsPath } from "./runtime-settings-api";

describe("processingRuntimeSettingsPath", () => {
  it("uses Processing runtime-settings route", () => {
    expect(processingRuntimeSettingsPath()).toBe(
      "/api/v1/processing/runtime-settings",
    );
  });
});
