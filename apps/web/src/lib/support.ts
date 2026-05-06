export function normalizeSupportUrl(
  raw: string | null | undefined,
): string | null {
  const value = (raw ?? "").trim();
  if (value === "") {
    return null;
  }
  try {
    const parsed = new URL(value);
    if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
      return null;
    }
    return parsed.toString();
  } catch {
    return null;
  }
}

export function shouldShowSupportPlaceholder(
  isDev: boolean,
  supportUrl: string | null,
): boolean {
  return isDev && supportUrl === null;
}

export const SUPPORT_URL = normalizeSupportUrl(
  import.meta.env.VITE_SUPPORT_URL,
);
export const SHOW_SUPPORT_URL_PLACEHOLDER = shouldShowSupportPlaceholder(
  import.meta.env.DEV,
  SUPPORT_URL,
);
