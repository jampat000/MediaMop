/**
 * Issue #496: the regional language variants `Weir.Core.Rules.LanguageVariants` can detect and
 * match on, so the web audio/subtitle language pickers can offer a variant identifier (e.g.
 * `fre-CA`) alongside its base language (`fre`) — a rule that names a variant only matches that
 * variant; a rule that names the base language still matches every variant, unchanged.
 *
 * Kept in sync by hand with the C# table (`apps/server/src/Weir.Core/Rules/LanguageVariants.cs`):
 * same identifiers, same display names, same base language per entry.
 */
export interface RefinerLanguageVariantOption {
  /** The identifier a rule set stores, e.g. "fre-CA". */
  code: string;
  /** e.g. "French (Canada)". */
  label: string;
  /** The base language code this variant refines, e.g. "fre". */
  baseCode: string;
}

export const REFINER_LANGUAGE_VARIANT_OPTIONS: readonly RefinerLanguageVariantOption[] =
  [
    { code: "fre-CA", label: "French (Canada)", baseCode: "fre" },
    { code: "fre-FR", label: "French (France)", baseCode: "fre" },
    { code: "fre-BE", label: "French (Belgium)", baseCode: "fre" },
    { code: "spa-ES", label: "Spanish (Spain)", baseCode: "spa" },
    { code: "spa-419", label: "Spanish (Latin America)", baseCode: "spa" },
    { code: "por-BR", label: "Portuguese (Brazil)", baseCode: "por" },
    { code: "por-PT", label: "Portuguese (Portugal)", baseCode: "por" },
    { code: "zho-Hant", label: "Chinese (Traditional)", baseCode: "zho" },
    { code: "zho-Hans", label: "Chinese (Simplified)", baseCode: "zho" },
    { code: "yue", label: "Cantonese", baseCode: "zho" },
    { code: "cmn", label: "Mandarin", baseCode: "zho" },
    { code: "nld-BE", label: "Flemish", baseCode: "nld" },
  ] as const;

/** Every variant declared for a given base language code, in table order. */
export function refinerLanguageVariantsFor(
  baseCode: string,
): readonly RefinerLanguageVariantOption[] {
  return REFINER_LANGUAGE_VARIANT_OPTIONS.filter(
    (v) => v.baseCode === baseCode,
  );
}
