import { describe, expect, it } from "vitest";
import { REFINER_STATUS_HANDLER_OK_FINALIZE_FAILED } from "./refiner-job-status-labels";
import { showRecoverFinalizeFailureControl } from "./refiner-recover-eligibility";

describe("showRecoverFinalizeFailureControl", () => {
  it("shows only for handler_ok_finalize_failed and admin/operator", () => {
    expect(showRecoverFinalizeFailureControl("admin", REFINER_STATUS_HANDLER_OK_FINALIZE_FAILED)).toBe(true);
    expect(showRecoverFinalizeFailureControl("operator", REFINER_STATUS_HANDLER_OK_FINALIZE_FAILED)).toBe(
      true,
    );
    expect(showRecoverFinalizeFailureControl("viewer", REFINER_STATUS_HANDLER_OK_FINALIZE_FAILED)).toBe(false);
    expect(showRecoverFinalizeFailureControl(undefined, REFINER_STATUS_HANDLER_OK_FINALIZE_FAILED)).toBe(
      false,
    );
  });

  it("hides for ordinary failed", () => {
    expect(showRecoverFinalizeFailureControl("admin", "failed")).toBe(false);
  });
});
