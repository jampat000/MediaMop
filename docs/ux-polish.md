# UX Polish Standard

This is the app-wide UX baseline for Weir. Use it when reviewing screens before release.

## Language

- User-facing text explains what happened and why in plain language.
- Avoid raw internal event keys, auth implementation names, library names, traceback wording, or JSON blobs unless the user explicitly opens a technical details view.
- Activity events describe the user outcome first, then technical detail second.
- Logs are system/application event logs for troubleshooting runtime issues, not a development changelog.

## Layout

**Superseded for page bodies:** [`design/content-language.md`](design/content-language.md)
is the standing spec for what sits inside a workspace panel, page by page as each is
converted. Its rule 3 forbids a card, panel, box or tile anywhere below a page's lead
band and figure row — the three "card" bullets below describe the pre-redesign layout
and apply only to what content-language.md's chrome-freeze leaves alone (the sidebar,
top bar, page header and tab row) and to dialogs, not to a converted page's body.
Every page listed in `design/redesign-docs-impact.md` has now converted (#588, #592,
#593, #596, #597, #599, #600, #601), so the card bullets no longer describe any page's
default body. The exception is Settings, where #599 applied the redesign sparingly and
deliberately left the action cards in place — Backup and restore in particular. Treat
content-language.md as the tie-breaker, not this file.

- Cards in the same section should use consistent spacing, action placement, and visual weight.
- Primary card actions should sit at the bottom of the card unless the control needs to remain inline for usability.
- Settings cards should be grouped by user task, not backend implementation.
- Multi-section product areas use the same themed horizontal section bar in Processing and Settings. It scrolls horizontally on narrow screens while preserving the tab-to-panel accessibility contract.
- Home and Activity remain task-focused pages rather than duplicating the section bar. Home is the main screen: what Weir holds now and anything that needs a person; searchable history and full job lists belong in Activity and Processing's Jobs section.
- The document is the page scroll owner. Do not trap signed-in pages inside a fixed-height nested scrolling pane.
- Empty states should be compact, aligned with the surrounding layout, and explain what to do next.
- Long detail views should be compressed by default and expandable when more information is useful.

## Visuals

- Status colors must be consistent:
  - healthy or complete: green
  - warning or review needed: amber
  - failed or blocked: red
  - informational or queued: blue/neutral
- Bubbles, badges, and pills should use the same shape language across Home, Activity, Settings, and Processing.
  **Unfulfilled, and it has diverged rather than merely lagged.** Now that every page in
  [`design/redesign-docs-impact.md`](design/redesign-docs-impact.md) has converted, there are three
  shape families, not one: Home grew its own `mm-home-row__state`, Activity kept
  `mm-activity-chip` / `mm-status-badge`, and Processing and Settings use the redesign's
  `mm-quiet-badge` / `mm-quiet-state`. The rule stays as written — it is the target — but closing it
  is now a deliberate consolidation, not something the remaining conversions will deliver on their own.
- Font sizing should stay consistent across headings, labels, body text, and compact metadata.

## Screen-specific baseline

- Home shows useful operational status, not just navigation.
- Activity is live, user-friendly, filterable, searchable, color-coded, and readable at scale.
- Processing activity can show before/after file details, size savings, languages, subtitles, and removals in an expandable layout. Still true after Files converted in #600: the detail lives in the expandable **Processing record** entry in a file's history, which labels source and output file and size, space saved, the processing plan, output validation, source cleanup and duration, with the raw payload behind a further `<details>`. It is an expandable row rather than a card now; the behaviour this bullet asks for is unchanged.
- Settings General groups setup wizard, timezone, log retention, and display density cleanly.
- Backup/Restore and Upgrade belong together as operational safety controls.
- Folder path inputs that need user-selected paths should support browsing where technically possible and allow manual local, Docker, and UNC-style paths.

## Review rule

If a screen looks technically correct but a normal user would not understand what happened or what to do next, it is not done.
