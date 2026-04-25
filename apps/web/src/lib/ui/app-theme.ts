/** Browser-local color theme; not synced to the server and safe to change instantly. */

export const APP_THEME_STORAGE_KEY = "mediamop-app-theme";

export type AppTheme = "dark" | "light";

export function parseAppTheme(raw: string | null): AppTheme {
  return raw === "light" ? "light" : "dark";
}

export function readStoredAppTheme(): AppTheme {
  try {
    return parseAppTheme(localStorage.getItem(APP_THEME_STORAGE_KEY));
  } catch {
    return "dark";
  }
}

export function applyAppThemeToDocument(theme: AppTheme): void {
  document.documentElement.setAttribute("data-mm-theme", theme);
}

export function persistAppTheme(theme: AppTheme): void {
  try {
    localStorage.setItem(APP_THEME_STORAGE_KEY, theme);
  } catch {
    /* private mode / blocked storage */
  }
  applyAppThemeToDocument(theme);
}

