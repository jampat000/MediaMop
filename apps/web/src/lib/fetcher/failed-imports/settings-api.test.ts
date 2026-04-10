import { describe, expect, it } from "vitest";
import { failedImportFetcherSettingsPath } from "./settings-api";

describe("failedImportFetcherSettingsPath", () => {
  it("uses Fetcher failed-imports settings route", () => {
    expect(failedImportFetcherSettingsPath()).toBe("/api/v1/fetcher/failed-imports/settings");
  });
});
