import { describe, expect, it } from "vitest";
import { failedImportManualQueuePassResultMessage } from "./enqueue-messages";

describe("failedImportManualQueuePassResultMessage", () => {
  it("distinguishes created vs already-present queue pass", () => {
    expect(
      failedImportManualQueuePassResultMessage({
        job_id: 1,
        dedupe_key: "k",
        job_kind: "x",
        queue_outcome: "created",
      }),
    ).toMatch(/added —/i);
    expect(
      failedImportManualQueuePassResultMessage({
        job_id: 1,
        dedupe_key: "k",
        job_kind: "x",
        queue_outcome: "already_present",
      }),
    ).toMatch(/already on the list/i);
  });
});
