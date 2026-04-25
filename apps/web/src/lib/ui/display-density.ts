/** Browser-local UI density; not synced to the server (easy to revert / no migration). */

export const DISPLAY_DENSITY_STORAGE_KEY = "mediamop-display-density";

export type DisplayDensity = "default" | "compact" | "comfortable" | "expanded";

export function parseDisplayDensity(raw: string | null): DisplayDensity {
  if (raw === "compact" || raw === "comfortable" || raw === "expanded") {
    return raw;
  }
  return "default";
}

export function readStoredDisplayDensity(): DisplayDensity {
  try {
    return parseDisplayDensity(localStorage.getItem(DISPLAY_DENSITY_STORAGE_KEY));
  } catch {
    return "default";
  }
}

export function applyDisplayDensityToDocument(density: DisplayDensity): void {
  const root = document.documentElement;
  if (density === "default") {
    root.removeAttribute("data-mm-density");
  } else {
    root.setAttribute("data-mm-density", density);
  }
}

export function persistDisplayDensity(density: DisplayDensity): void {
  try {
    if (density === "default") {
      localStorage.removeItem(DISPLAY_DENSITY_STORAGE_KEY);
    } else {
      localStorage.setItem(DISPLAY_DENSITY_STORAGE_KEY, density);
    }
  } catch {
    /* private mode / blocked storage */
  }
  applyDisplayDensityToDocument(density);
}
