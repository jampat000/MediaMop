import { describe, expect, it } from "vitest";
import {
  normalizeSupportUrl,
  shouldShowSupportCard,
  shouldShowSupportPlaceholder,
} from "./support";

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
    expect(normalizeSupportUrl("mailto:support@example.com")).toBeNull();
    expect(normalizeSupportUrl("file:///tmp/support-link")).toBeNull();
  });

  it("only shows placeholder in development when no URL is configured", () => {
    expect(shouldShowSupportPlaceholder(true, null)).toBe(true);
    expect(shouldShowSupportPlaceholder(false, null)).toBe(false);
    expect(
      shouldShowSupportPlaceholder(true, "https://github.com/sponsors/example"),
    ).toBe(false);
  });

  it("only shows the support card in production when URL is valid", () => {
    expect(shouldShowSupportCard(false, null)).toBe(false);
    expect(
      shouldShowSupportCard(false, "https://github.com/sponsors/example"),
    ).toBe(true);
    expect(shouldShowSupportCard(true, null)).toBe(true);
  });
});
