import { describe, expect, it } from "vitest";
import { FAILED_IMPORT_STATUS_HANDLER_OK_FINALIZE_FAILED } from "./task-status-labels";
import { showFailedImportManualEnqueueControl, showFailedImportRecoverControl } from "./eligibility";

describe("failed-import control eligibility", () => {
  it("allows manual enqueue for admin and operator only", () => {
    expect(showFailedImportManualEnqueueControl(undefined)).toBe(false);
    expect(showFailedImportManualEnqueueControl("viewer")).toBe(false);
    expect(showFailedImportManualEnqueueControl("admin")).toBe(true);
    expect(showFailedImportManualEnqueueControl("operator")).toBe(true);
  });

  it("allows recover only for handler_ok_finalize_failed and admin/operator", () => {
    expect(showFailedImportRecoverControl("admin", FAILED_IMPORT_STATUS_HANDLER_OK_FINALIZE_FAILED)).toBe(true);
    expect(showFailedImportRecoverControl("operator", FAILED_IMPORT_STATUS_HANDLER_OK_FINALIZE_FAILED)).toBe(true);
    expect(showFailedImportRecoverControl("admin", "failed")).toBe(false);
    expect(showFailedImportRecoverControl("viewer", FAILED_IMPORT_STATUS_HANDLER_OK_FINALIZE_FAILED)).toBe(false);
  });
});
