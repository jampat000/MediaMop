import { describe, expect, it } from "vitest";
import { FAILED_IMPORT_STATUS_HANDLER_OK_FINALIZE_FAILED } from "./task-status-labels";
import { FAILED_IMPORT_INSPECTION_FILTER_OPTIONS } from "./inspection-filter-labels";

function labelFor(value: string): string | undefined {
  return FAILED_IMPORT_INSPECTION_FILTER_OPTIONS.find((o) => o.value === value)?.label;
}

describe("FAILED_IMPORT_INSPECTION_FILTER_OPTIONS", () => {
  it("keeps needs-manual-finish filter distinct and names the stored status for honesty", () => {
    const h = labelFor(FAILED_IMPORT_STATUS_HANDLER_OK_FINALIZE_FAILED);
    const f = labelFor("failed");
    expect(h).toBeDefined();
    expect(f).toBeDefined();
    expect(h).not.toBe(f);
    expect(h!.toLowerCase()).toContain("handler_ok_finalize_failed");
    expect(f!.toLowerCase()).toContain("failed");
    expect(f!.toLowerCase()).not.toContain("handler_ok_finalize_failed");
  });

  it("uses plain default finished wording for the terminal bucket", () => {
    const t = labelFor("terminal");
    expect(t!.toLowerCase()).toContain("finished");
    expect(t!.toLowerCase()).toContain("default");
    expect(t!.toLowerCase()).toContain("manual finish");
  });

  it("lists every filter value exactly once", () => {
    const values = FAILED_IMPORT_INSPECTION_FILTER_OPTIONS.map((o) => o.value);
    expect(new Set(values).size).toBe(values.length);
    expect(values).toContain("terminal");
    expect(values).toContain("pending");
    expect(values).toContain("leased");
  });
});
