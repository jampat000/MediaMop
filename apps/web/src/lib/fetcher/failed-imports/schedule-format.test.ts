import { describe, expect, it } from "vitest";
import { formatScheduleIntervalSeconds } from "./schedule-format";

describe("formatScheduleIntervalSeconds", () => {
  it("formats hours when divisible by 3600", () => {
    expect(formatScheduleIntervalSeconds(3600)).toMatch(/1 h/);
    expect(formatScheduleIntervalSeconds(3600)).toContain("3600");
  });

  it("formats minutes when divisible by 60", () => {
    expect(formatScheduleIntervalSeconds(120)).toMatch(/2 min/);
  });

  it("falls back to seconds", () => {
    expect(formatScheduleIntervalSeconds(45)).toBe("45 s");
  });
});
