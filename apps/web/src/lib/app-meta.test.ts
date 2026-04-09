import { describe, expect, it } from "vitest";
import { WEB_APP_VERSION } from "./app-meta";

describe("WEB_APP_VERSION", () => {
  it("is injected from package.json at build time", () => {
    expect(typeof WEB_APP_VERSION).toBe("string");
    expect(WEB_APP_VERSION.length).toBeGreaterThan(0);
    expect(WEB_APP_VERSION).toMatch(/^\d+\.\d+\.\d+/);
  });
});
