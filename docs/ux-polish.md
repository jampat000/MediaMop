# UX Polish Standard

This is the app-wide UX baseline for MediaMop. Use it when reviewing screens before release.

## Language

- User-facing text explains what happened and why in plain language.
- Avoid raw internal event keys, auth implementation names, library names, traceback wording, or JSON blobs unless the user explicitly opens a technical details view.
- Activity events describe the user outcome first, then technical detail second.
- Logs are system/application event logs for troubleshooting runtime issues, not a development changelog.

## Layout

- Cards in the same section should use consistent spacing, action placement, and visual weight.
- Primary card actions should sit at the bottom of the card unless the control needs to remain inline for usability.
- Settings cards should be grouped by user task, not backend implementation.
- Multi-section product areas use the same themed horizontal section bar in Refiner and Settings. It scrolls horizontally on narrow screens while preserving the tab-to-panel accessibility contract.
- In hand and Activity remain task-focused pages rather than duplicating the section bar. In hand is the main screen: what MediaMop holds now and anything that needs a person; searchable history and full job lists belong in Activity and Refiner's Jobs section.
- The document is the page scroll owner. Do not trap signed-in pages inside a fixed-height nested scrolling pane.
- Empty states should be compact, aligned with the surrounding layout, and explain what to do next.
- Long detail views should be compressed by default and expandable when more information is useful.

## Visuals

- Status colors must be consistent:
  - healthy or complete: green
  - warning or review needed: amber
  - failed or blocked: red
  - informational or queued: blue/neutral
- Bubbles, badges, and pills should use the same shape language across In hand, Activity, Settings, and Refiner.
- Font sizing should stay consistent across headings, labels, body text, and compact metadata.

## Screen-specific baseline

- In hand shows useful operational status, not just navigation.
- Activity is live, user-friendly, filterable, searchable, color-coded, and readable at scale.
- Refiner activity can show before/after file details, size savings, languages, subtitles, and removals in an expandable layout.
- Settings General groups setup wizard, timezone, log retention, and display density cleanly.
- Backup/Restore and Upgrade belong together as operational safety controls.
- Folder path inputs that need user-selected paths should support browsing where technically possible and allow manual local, Docker, and UNC-style paths.

## Review rule

If a screen looks technically correct but a normal user would not understand what happened or what to do next, it is not done.
