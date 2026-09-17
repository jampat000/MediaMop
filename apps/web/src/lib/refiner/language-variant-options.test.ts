import { describe, expect, it } from "vitest";
import {
  REFINER_LANGUAGE_VARIANT_OPTIONS,
  refinerLanguageVariantsFor,
} from "./language-variant-options";

describe("refinerLanguageVariantsFor", () => {
  it("lists every French variant under the French base code", () => {
    const codes = refinerLanguageVariantsFor("fre").map((v) => v.code);
    expect(codes).toEqual(
      expect.arrayContaining(["fre-CA", "fre-FR", "fre-BE"]),
    );
  });

  it("lists Cantonese and Mandarin under the Chinese base code", () => {
    const codes = refinerLanguageVariantsFor("zho").map((v) => v.code);
    expect(codes).toEqual(
      expect.arrayContaining(["zho-Hant", "zho-Hans", "yue", "cmn"]),
    );
  });

  it("returns nothing for a language with no configured variants", () => {
    expect(refinerLanguageVariantsFor("eng")).toEqual([]);
  });

  it("every option's baseCode matches what refinerLanguageVariantsFor returns it under", () => {
    for (const option of REFINER_LANGUAGE_VARIANT_OPTIONS) {
      expect(refinerLanguageVariantsFor(option.baseCode)).toContainEqual(
        option,
      );
    }
  });

  it("has no duplicate identifiers", () => {
    const codes = REFINER_LANGUAGE_VARIANT_OPTIONS.map((v) => v.code);
    expect(new Set(codes).size).toBe(codes.length);
  });
});
