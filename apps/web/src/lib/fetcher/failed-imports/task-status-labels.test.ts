import { describe, expect, it } from "vitest";
import {
  FAILED_IMPORT_STATUS_HANDLER_OK_FINALIZE_FAILED,
  failedImportTaskStatusPrimaryLabel,
} from "./task-status-labels";

describe("failedImportTaskStatusPrimaryLabel", () => {
  it("keeps needs-manual-finish distinct from ordinary failed", () => {
    const finalize = failedImportTaskStatusPrimaryLabel(FAILED_IMPORT_STATUS_HANDLER_OK_FINALIZE_FAILED);
    const failed = failedImportTaskStatusPrimaryLabel("failed");
    expect(finalize.toLowerCase()).toContain("manual");
    expect(failed.toLowerCase()).toContain("error");
    expect(finalize).not.toBe(failed);
  });

  it("covers common persisted statuses", () => {
    expect(failedImportTaskStatusPrimaryLabel("completed")).toBe("Completed");
    expect(failedImportTaskStatusPrimaryLabel("leased")).toContain("progress");
    expect(failedImportTaskStatusPrimaryLabel("pending")).toContain("Waiting");
  });
});
