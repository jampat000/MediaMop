import { describe, expect, it } from "vitest";
import { normalizeSupportUrl, shouldShowSupportPlaceholder } from "./support";

describe("support helpers", () => {
  it("accepts http and https URLs", () => {
    expect(normalizeSupportUrl("https://github.com/sponsors/example")).toBe(
      "https://github.com/sponsors/example",
    );
    expect(normalizeSupportUrl("http://example.com/support")).toBe(
      "http://example.com/support",
    );
  });

  it("rejects blank and invalid URLs", () => {
    expect(normalizeSupportUrl("")).toBeNull();
    expect(normalizeSupportUrl("   ")).toBeNull();
    expect(normalizeSupportUrl("not-a-url")).toBeNull();
    expect(normalizeSupportUrl("javascript:alert(1)")).toBeNull();
  });

  it("only shows placeholder in development when no URL is configured", () => {
    expect(shouldShowSupportPlaceholder(true, null)).toBe(true);
    expect(shouldShowSupportPlaceholder(false, null)).toBe(false);
    expect(
      shouldShowSupportPlaceholder(true, "https://github.com/sponsors/example"),
    ).toBe(false);
  });
});
