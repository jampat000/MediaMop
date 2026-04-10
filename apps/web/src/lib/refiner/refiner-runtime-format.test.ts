import { describe, expect, it } from "vitest";
import { formatScheduleIntervalSeconds } from "./refiner-runtime-format";

describe("formatScheduleIntervalSeconds", () => {
  it("formats whole hours", () => {
    expect(formatScheduleIntervalSeconds(3600)).toBe("1 h (3600 s)");
    expect(formatScheduleIntervalSeconds(7200)).toBe("2 h (7200 s)");
  });

  it("formats whole minutes when not a whole hour", () => {
    expect(formatScheduleIntervalSeconds(1800)).toBe("30 min (1800 s)");
  });

  it("falls back to seconds", () => {
    expect(formatScheduleIntervalSeconds(90)).toBe("90 s");
  });
});
