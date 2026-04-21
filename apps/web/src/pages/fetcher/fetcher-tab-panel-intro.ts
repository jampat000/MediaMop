import { mmModuleTabBlurbTextClass } from "../../lib/ui/mm-module-tab-blurb";

/**
 * Shared top-of-panel rhythm for Fetcher section tabs (Connections, Sonarr, Radarr, Schedules).
 * Heading → optional one-line blurb → first card/section.
 */
export const FETCHER_TAB_PANEL_INTRO_CLASS =
  "border-b border-[var(--mm-border)] pb-3.5 mb-5 sm:pb-4 sm:mb-5";

export const FETCHER_TAB_PANEL_TITLE_CLASS = "mm-page__title text-xl sm:text-2xl";

/** Blurb under an in-tab `h2` — adds `mt-1` below the title; base typography matches module tab blurbs. */
export const FETCHER_TAB_PANEL_BLURB_CLASS = `mt-1 ${mmModuleTabBlurbTextClass}`;
