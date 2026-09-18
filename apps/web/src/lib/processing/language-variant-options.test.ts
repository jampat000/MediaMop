import { describe, expect, it } from "vitest";
import {
  PROCESSING_LANGUAGE_VARIANT_OPTIONS,
  processingLanguageVariantsFor,
} from "./language-variant-options";

describe("processingLanguageVariantsFor", () => {
  it("lists every French variant under the French base code", () => {
    const codes = processingLanguageVariantsFor("fre").map((v) => v.code);
    expect(codes).toEqual(
      expect.arrayContaining(["fre-CA", "fre-FR", "fre-BE"]),
    );
  });

  it("lists Cantonese and Mandarin under the Chinese base code", () => {
    const codes = processingLanguageVariantsFor("zho").map((v) => v.code);
    expect(codes).toEqual(
      expect.arrayContaining(["zho-Hant", "zho-Hans", "yue", "cmn"]),
    );
  });

  it("returns nothing for a language with no configured variants", () => {
    expect(processingLanguageVariantsFor("eng")).toEqual([]);
  });

  it("every option's baseCode matches what processingLanguageVariantsFor returns it under", () => {
    for (const option of PROCESSING_LANGUAGE_VARIANT_OPTIONS) {
      expect(processingLanguageVariantsFor(option.baseCode)).toContainEqual(
        option,
      );
    }
  });

  it("has no duplicate identifiers", () => {
    const codes = PROCESSING_LANGUAGE_VARIANT_OPTIONS.map((v) => v.code);
    expect(new Set(codes).size).toBe(codes.length);
  });
});
