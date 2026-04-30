/** ISO-639-3 codes + English labels for operator stream-language picks. */
export const REFINER_STREAM_LANGUAGE_OPTIONS: readonly {
  code: string;
  label: string;
}[] = [
  { code: "eng", label: "English" },
  { code: "jpn", label: "Japanese" },
  { code: "spa", label: "Spanish" },
  { code: "fre", label: "French" },
  { code: "deu", label: "German" },
  { code: "ita", label: "Italian" },
  { code: "por", label: "Portuguese" },
  { code: "rus", label: "Russian" },
  { code: "zho", label: "Chinese" },
  { code: "kor", label: "Korean" },
  { code: "hin", label: "Hindi" },
  { code: "ara", label: "Arabic" },
  { code: "pol", label: "Polish" },
  { code: "tur", label: "Turkish" },
  { code: "swe", label: "Swedish" },
  { code: "dan", label: "Danish" },
  { code: "fin", label: "Finnish" },
  { code: "nld", label: "Dutch" },
  { code: "nor", label: "Norwegian" },
  { code: "hun", label: "Hungarian" },
  { code: "ces", label: "Czech" },
  { code: "ell", label: "Greek" },
  { code: "heb", label: "Hebrew" },
  { code: "tha", label: "Thai" },
  { code: "vie", label: "Vietnamese" },
  { code: "ukr", label: "Ukrainian" },
  { code: "ron", label: "Romanian" },
  { code: "ind", label: "Indonesian" },
  { code: "msa", label: "Malay" },
  { code: "und", label: "Undetermined" },
] as const;

export function refinerStreamLanguageLabel(
  code: string | null | undefined,
): string {
  const c = (code ?? "").trim().toLowerCase();
  if (!c) {
    return "—";
  }
  const hit = REFINER_STREAM_LANGUAGE_OPTIONS.find((o) => o.code === c);
  return hit ? hit.label : c;
}
