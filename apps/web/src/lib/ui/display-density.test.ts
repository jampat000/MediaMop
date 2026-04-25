import { describe, expect, it } from "vitest";
import { DISPLAY_DENSITY_STORAGE_KEY, parseDisplayDensity, readStoredDisplayDensity } from "./display-density";

describe("display-density", () => {
  it("parses stored values", () => {
    expect(parseDisplayDensity(null)).toBe("default");
    expect(parseDisplayDensity("")).toBe("default");
    expect(parseDisplayDensity("comfortable")).toBe("comfortable");
    expect(parseDisplayDensity("compact")).toBe("compact");
    expect(parseDisplayDensity("expanded")).toBe("expanded");
    expect(parseDisplayDensity("nope")).toBe("default");
  });

  it("reads from localStorage", () => {
    localStorage.setItem(DISPLAY_DENSITY_STORAGE_KEY, "compact");
    expect(readStoredDisplayDensity()).toBe("compact");
    localStorage.removeItem(DISPLAY_DENSITY_STORAGE_KEY);
    expect(readStoredDisplayDensity()).toBe("default");
  });
});
