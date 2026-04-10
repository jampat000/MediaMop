import { describe, expect, it } from "vitest";
import { failedImportEnqueueResultMessage } from "./enqueue-messages";

describe("failedImportEnqueueResultMessage", () => {
  it("distinguishes created vs deduped enqueue", () => {
    expect(
      failedImportEnqueueResultMessage({
        job_id: 1,
        dedupe_key: "k",
        job_kind: "x",
        enqueue_outcome: "created",
      }),
    ).toMatch(/queued now/i);
    expect(
      failedImportEnqueueResultMessage({
        job_id: 1,
        dedupe_key: "k",
        job_kind: "x",
        enqueue_outcome: "already_present",
      }),
    ).toMatch(/already queued/i);
  });
});
