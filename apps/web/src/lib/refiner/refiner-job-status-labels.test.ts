import { describe, expect, it } from "vitest";
import {
  REFINER_STATUS_HANDLER_OK_FINALIZE_FAILED,
  isHandlerOkFinalizeFailedStatus,
  refinerJobStatusPrimaryLabel,
} from "./refiner-job-status-labels";

describe("refinerJobStatusPrimaryLabel", () => {
  it("makes handler_ok_finalize_failed explicit and distinct from failed", () => {
    const finalize = refinerJobStatusPrimaryLabel(REFINER_STATUS_HANDLER_OK_FINALIZE_FAILED);
    const failed = refinerJobStatusPrimaryLabel("failed");
    expect(finalize).not.toBe(failed);
    expect(finalize.toLowerCase()).toMatch(/finish|finalize/);
    expect(failed.toLowerCase()).not.toContain("finish");
  });

  it("labels completed, queued, and running", () => {
    expect(refinerJobStatusPrimaryLabel("completed")).toBe("Completed");
    expect(refinerJobStatusPrimaryLabel("leased")).toContain("Running");
    expect(refinerJobStatusPrimaryLabel("pending")).toContain("Queued");
  });
});

describe("isHandlerOkFinalizeFailedStatus", () => {
  it("is true only for handler_ok_finalize_failed", () => {
    expect(isHandlerOkFinalizeFailedStatus(REFINER_STATUS_HANDLER_OK_FINALIZE_FAILED)).toBe(true);
    expect(isHandlerOkFinalizeFailedStatus("failed")).toBe(false);
  });
});
