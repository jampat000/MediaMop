/** ISO 639-1 → English display name (Subber UI). */

export const SUBBER_LANGUAGE_BY_CODE: Record<string, string> = {
  en: "English",
  fr: "French",
  de: "German",
  es: "Spanish",
  it: "Italian",
  pt: "Portuguese",
  nl: "Dutch",
  pl: "Polish",
  ru: "Russian",
  ja: "Japanese",
  zh: "Chinese",
  ko: "Korean",
  ar: "Arabic",
  sv: "Swedish",
  da: "Danish",
  fi: "Finnish",
  no: "Norwegian",
  tr: "Turkish",
};

export const SUBBER_LANGUAGE_OPTIONS = Object.entries(SUBBER_LANGUAGE_BY_CODE).map(([code, label]) => ({
  code,
  label,
}));

export function subberLanguageLabel(code: string): string {
  return SUBBER_LANGUAGE_BY_CODE[code.toLowerCase()] ?? code.toUpperCase();
}
