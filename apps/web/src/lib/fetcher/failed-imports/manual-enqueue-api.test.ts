import { describe, expect, it } from "vitest";
import { failedImportRadarrEnqueuePath, failedImportSonarrEnqueuePath } from "./manual-enqueue-api";

describe("Fetcher failed-import manual queue POST path helpers", () => {
  it("uses distinct Radarr and Sonarr POST URLs under /api/v1/fetcher/failed-imports", () => {
    expect(failedImportRadarrEnqueuePath()).toBe("/api/v1/fetcher/failed-imports/radarr/enqueue");
    expect(failedImportSonarrEnqueuePath()).toBe("/api/v1/fetcher/failed-imports/sonarr/enqueue");
  });
});
