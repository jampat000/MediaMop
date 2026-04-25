import { afterEach, describe, expect, it } from "vitest";
import {
  APP_THEME_STORAGE_KEY,
  applyAppThemeToDocument,
  parseAppTheme,
  persistAppTheme,
  readStoredAppTheme,
} from "./app-theme";

describe("app-theme", () => {
  afterEach(() => {
    localStorage.removeItem(APP_THEME_STORAGE_KEY);
    document.documentElement.removeAttribute("data-mm-theme");
  });

  it("parses stored values", () => {
    expect(parseAppTheme(null)).toBe("dark");
    expect(parseAppTheme("")).toBe("dark");
    expect(parseAppTheme("dark")).toBe("dark");
    expect(parseAppTheme("light")).toBe("light");
    expect(parseAppTheme("nope")).toBe("dark");
  });

  it("reads from localStorage", () => {
    localStorage.setItem(APP_THEME_STORAGE_KEY, "light");
    expect(readStoredAppTheme()).toBe("light");
    localStorage.removeItem(APP_THEME_STORAGE_KEY);
    expect(readStoredAppTheme()).toBe("dark");
  });

  it("applies and persists the document theme", () => {
    applyAppThemeToDocument("light");
    expect(document.documentElement.getAttribute("data-mm-theme")).toBe("light");
    persistAppTheme("dark");
    expect(localStorage.getItem(APP_THEME_STORAGE_KEY)).toBe("dark");
    expect(document.documentElement.getAttribute("data-mm-theme")).toBe("dark");
  });
});
