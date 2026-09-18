# Site QA: every screen against the content language

Six pages were converted to [the content language](content-language.md) by six agents
working in parallel, and each verified its own page. This is the first pass that looked at
the whole site together. It lists every defect found, what was fixed, what was left and
why, and what was checked and found clean.

**Method.** 25 screens × dark and light × 1440 and 390 wide × seeded and fresh-empty: 200
screenshots from `scripts/screenshot-site.py`. The harness shot only Settings > General
before; it now shoots all seven Settings tabs, and the six it had never shot were where most
of the survivors were. Anything that could be measured was measured in a live browser
rather than judged by eye. Those numbers are quoted below.

**Out of scope.** Settings > General and the setup wizard were converted on their own
branch (#613) and are not reviewed here. The chrome (sidebar, top bar, page header, tab row)
is frozen.

## Count by category

| Category                     | Found | Fixed | Left |
| ---------------------------- | ----: | ----: | ---: |
| 1 · Ragged alignment         |     4 |     4 |    0 |
| 2 · Orphans                  |     6 |     6 |    0 |
| 3 · Nested boundaries        |     4 |     4 |    0 |
| 4 · Survivors                |     5 |     5 |    0 |
| 5 · Inconsistency            |     4 |     4 |    0 |
| 6 · Spacing rhythm           |     2 |     2 |    0 |
| 7 · Looks wrong              |     3 |     3 |    0 |
| **Total**                    |**28** |**28** |**0** |

Severity: **High** is visible at first glance on a page's main path. **Medium** is visible to
anyone looking. **Low** needs a particular state, width or install type.

## Defects

### 1 · Ragged alignment

| #  | Screen | File | Severity | What was wrong | Status |
| -- | ------ | ---- | -------- | -------------- | ------ |
| A1 | Processing Overview, Home, Files (every lead band) | `weir-content.css` | High | The band's numbers did not sit on one line, on the approved reference included. Measured at 1440 from each segment's top: Overview 62/62/56/62/81/62 px, Home spread 29 px, Files 19 px, and similar at every other width. A segment is a wrapping flex container, so `align-content: normal` shared the band's spare height *between* its label, number and hint lines, and a segment with no hint dropped its number furthest. The label's two reserved lines were also the wrong line-height and sized in `em`, so they shrank on the narrowest segments. | **Fixed.** Every label's text now sits at 17 px and every number's baseline at 84 px, in every segment on all three pages. Swept 390–1600 in 10 px steps: never wraps, never inverts (#608's promise holds), baselines within 1 px (sub-pixel rounding) at every width. |
| A2 | Library > Overview | `weir-content.css` | Medium | Three supporters are narrow enough that "Cannot be processed" wraps, so its number sat 18 px below the other two. | **Fixed.** A row with three supporters reserves two label lines, so all three numbers sit at the same height. Rows with one or two supporters (Processing, Home) are unchanged. |
| A3 | Processing > Audio & subtitles | `processing-rule-set-workspace.tsx` | High | The five numbered groups sat in two columns: "Audio" three times the height of "Subtitles" beside it, "Remove from container" taller than "Original language", and nothing lined up. The owner's Settings complaint, on another page. | **Fixed.** One column in number order, capped at a readable form width. |
| A4 | Processing > Libraries, "Processing, safety and records" | `processing-process-settings-section.tsx` | Medium | Same two-column fault ("Throughput budget", 7 fields, beside "Admission safety", 3). The long label "Minimum unchanged age (seconds)" wrapped and pushed its input below its neighbour's. | **Fixed.** Groups in one column. Every input shares the capacity pair's column width and left edge. |

### 2 · Orphans

| #  | Screen | File | Severity | What was wrong | Status |
| -- | ------ | ---- | -------- | -------------- | ------ |
| O1 | Library > Overview, 721–1280 px | `weir-content.css` | Medium | The ≤1280 figure-row rule hard-codes two supporter columns, so the third supporter sat alone on its own row. Measured at 1280, 1024 and 800. | **Fixed.** Three supporters stay three across under the hero, as two stay two across. |
| O2 | Audio & subtitles | `processing-rule-set-workspace.tsx` | High | Group 5 "Track naming & chapters" sat alone with an empty column to its right. | **Fixed** by A3. |
| O3 | Audio & subtitles, "Remove from container" | `processing-rule-set-workspace.tsx` | Low | Five switches in two columns left "Other metadata" alone. | **Fixed.** One per row, as group 5 already did. |
| O4 | Libraries, "Throughput budget" | `processing-process-settings-section.tsx` | Low | Seven fields in two columns left "Unknown-resolution cost" alone. | **Fixed.** The capacity pair, then the four resolution costs as one row of equals, then the exception on its own line at pair width. |
| O5 | Libraries, "Admission safety" | same | Low | Three fields in two columns left "Minimum free output space" alone. | **Fixed.** One per line. |
| O6 | Libraries, "Records and cleanup" | same | Low | The retention number sat alone in the first of three columns, with nothing under it beside the long list of switches. | **Fixed.** The number on its own line, the switches under it. |

### 3 · Nested boundaries

| #  | Screen | File | Severity | What was wrong | Status |
| -- | ------ | ---- | -------- | -------------- | ------ |
| N1 | Processing > Overview, fresh install | `processing-overview-tab.tsx`, `mm-overview-cards.tsx` | High | "Get started" was a bordered card holding three bordered step tiles. It is the first thing a new install shows, on the reference page itself. | **Fixed.** A quiet section with the steps as one column and "Set up libraries →" as a quiet link beside the heading. This is the shape Home's empty state already uses. |
| N2 | Settings > Upgrade (Windows installs) | `settings-upgrade-tab.tsx` | Medium | "Update mode" was a filled, shadowed panel holding bordered radio tiles. This is the same fault the owner saw in General. It is not in the screenshots because the harness install type is `source`. | **Fixed.** A quiet section with radio rows. |
| N3 | Settings > Notifications, editing or adding a channel | `settings-notifications-tab.tsx` | Medium | Both forms were a filled, bordered panel, one of them inside a table cell. | **Fixed.** Field groups. |
| N4 | Login | `login-page.tsx` | Low | "Trust this device" was a bordered, filled box inside the sign-in card. | **Fixed.** A checkbox row. |

### 4 · Survivors

| #  | Screen | File | Severity | What was wrong | Status |
| -- | ------ | ---- | -------- | -------------- | ------ |
| S1 | Settings > Security | `settings-security-tab.tsx` | High | "Change username" and "Change password" were `mm-card`s under three quiet sections. Their titles drew as small eyebrows while the quiet sections drew as headings, so one screen had two heading styles. | **Fixed.** Quiet sections. |
| S2 | Settings > Backup and restore | `settings-backup-tab.tsx` | High | Two cards in a two-column grid, the right one a third the height of the left, with full-width buttons found nowhere else on the site. | **Fixed.** Two field groups, stacked, inside a quiet section. |
| S3 | Settings > Media managers | `settings-media-managers-tab.tsx` | High | Never converted: a `grid gap-4` of cards, with no section structure and no page-level test id. | **Fixed.** Each connection is a quiet section, the add form is a field group, and the tab stands in `mm-quiet-stack` with `data-testid="suite-settings-media-managers"`. |
| S4 | Libraries, Direct play, Schedules: load failure | three `processing-*-section.tsx` | Medium | Red bordered boxes (`mm-module-surface`), not the language's `.mm-interrupt`. | **Fixed.** `.mm-interrupt`. |
| S5 | Audio & subtitles, no profiles | `processing-rule-set-workspace.tsx` | Low | "No profiles yet" was a dashed box. Every other empty state is a quiet sentence. | **Fixed.** |

### 5 · Inconsistency between pages

| #  | Screen | File | Severity | What was wrong | Status |
| -- | ------ | ---- | -------- | -------------- | ------ |
| C1 | Libraries, Audio & subtitles (×2), Logs, Notifications, Security | five files | Medium | The reference puts only `.mm-quiet-link`s with a trailing `→` beside a section heading. So do Home, Activity, Library, Upgrade and Logs' own "Show →". Five asides were bordered buttons instead, two of them primary-filled. | **Fixed.** Quiet links. Resting labels gain `→`, and busy labels drop it (as Activity's "Exporting…" does). What each control does is unchanged. Four assertions follow the labels, in three trees: `tests/e2e/weir/test_visual_smoke_audit.py`, `scripts/live-packaged-e2e.py` (×2; one is guarded by `if refresh.count()` and would have skipped silently), `processing-rule-set-workspace.test.tsx`. |
| C2 | Processing's two empty states | — | — | Overview used a card and Home used a quiet sentence. | **Fixed** by N1. |
| C3 | Schedules | `processing-schedules-section.tsx` | Low | TV then Movies. Libraries, the Overview table and Run now directly below all use Movies then TV. | **Fixed.** |
| C4 | Every form | many | Medium | Field labels were drawn two ways: an uppercase eyebrow on Activity filters, Jobs, Libraries' processing settings, Security, Backup, Upgrade, Logs, Notifications and the sign-in cards; sentence case on Files filters, the Library picker, Audio & subtitles, Media managers, Schedules and the library editor. | **Fixed, on James's call.** Every form field label is sentence case, `text-sm` in `--mm-text2`, including `.mm-auth-label` on sign-in and first run. The uppercase eyebrow stays on group titles, column heads, fact labels (`<dt>`) and card eyebrows only. |

### 6 · Spacing rhythm

| #  | Screen | File | Severity | What was wrong | Status |
| -- | ------ | ---- | -------- | -------------- | ------ |
| R1 | 10 pages, 19 notes | `weir-content.css` | Medium | `.mm-quiet-note` declared `margin: 0` in an unlayered rule. That silently cancelled the `mt-*` on every note that asked for spacing: the Tailwind trap `content-language.md` itself describes. Each note sat flush against the table or heading above it, and Maintenance's last two paragraphs read as one. On source order it also beat #609's `.mm-quiet-group__body > * + *` rhythm. | **Fixed.** Preflight already zeroes the margin, so the declaration is gone. |
| R2 | Login, Settings > Support, Setup wizard | `login-page.tsx`, `settings-support-tab.tsx`, `setup-wizard-page.tsx` | Low | The same trap in three more places: `mt-2` on `.mm-auth-lead`, `mt-3` on `.mm-quiet-table__sub`, `mt-4` on `.mm-auth-banner`. Unlike `.mm-quiet-note`, each class's own margin *is* deliberate for its main use (12, 13 and 4 other call sites rely on it), so the primitives stay and the call sites change. | **Fixed.** Login: the `mt-2` was dead and the gap above already came from the element before it, so it is removed with nothing visible changing. Support: the development note was borrowing a table class outside a table; it now uses plain caption type. Setup wizard: the banner's gap moved onto a wrapper, so it no longer sits flush against the last section. A rescan finds no `mm-*` class that sets a margin paired with a margin utility anywhere. |

### 7 · Looks wrong

| #  | Screen | File | Severity | What was wrong | Status |
| -- | ------ | ---- | -------- | -------------- | ------ |
| L1 | Overview, Success rate | `processing-overview-tab.tsx` | Medium | The caption read "3 finished · 1 failed" beside a Processed tile reading "2 files handed back". The number was the server's *terminal* count (`OverviewStatsStore`: completed + failed), not a count of successes. | **Fixed.** "2 succeeded · 1 failed". The zero case reads "Nothing finished yet", and the local is renamed `terminal` to match the server. |
| L2 | Light theme, 8 pages | processing and settings pages | Medium | Errors and confirmations used raw `text-red-200/300` and `text-emerald-200/300/400`, some on `red-950`/`emerald-950` washes. On the light theme these are near-invisible. | **Fixed.** `mm-status-text--failed` / `--healthy`, the tokens every converted page uses. |
| L3 | Libraries (upstream-signal badge), Try on a file (result pills) | `processing-libraries-section.tsx`, `processing-rules-preview-panel.tsx` | Low | The same raw emerald/red/amber palette, on badges. | **Fixed, on James's call.** Processing > Files' token-based status pill is now shared as `mmStatusPillClass(tone)` in `lib/ui/mm-status-tone.ts` (healthy, info, warning, failed, neutral, all from `--mm-status-*`). The Libraries badge, both Try-on-a-file pills and Upgrade's status pill use it. The same sweep moved the last raw colours onto tokens: Upgrade's release strip and update-ready notice, the startup dots and the folder-picker notices. No raw palette class is left anywhere in `apps/web/src`. |

## Left deliberately

- **Upgrade's "Release status" strip** is filled and colour-coded. It is that page's lead,
  and the language allows one loud thing. Kept, now on the status tokens (L3).
- **Files: the per-row button clusters** ("Check again", "Pass through unchanged",
  "Processing record"…) are buttons in the quiet body. They are each file's primary
  operations, not links to elsewhere, so demoting six per row to text would change how the
  page feels to use. Kept. The same reasoning covers Activity's "Apply filters" and
  Maintenance's "Run for Movies / Run for TV".
- **Files' section heading** "Give every file a useful next step." is a sentence where every
  other heading is a noun phrase. This is copy, not layout. Left for whoever owns the wording.
- **"Try on a file" and "Advanced track ordering"** are disclosure rows inside the profile
  form, not section asides, so C1 does not apply. "Try on a file" is also asserted by five
  unit tests. Kept.
- **Media managers' "Add an app"** stays a button under the list. C1 is about controls
  beside a section heading, and this list has no heading to put one beside. Giving it
  one ("Connected apps") is a copy decision. Left.
- **The Metadata provider editor** (behind "Configure →") lays out its three fields as 1 + 2,
  then 2, which leaves one empty cell. It is only visible after a click. Minor. Left.

## Checked and found clean

- **Home**, seeded and empty, both themes, both widths. Its empty state (interrupt
  sentence plus quiet section) is the model the Processing empty state now follows.
- **Activity.** Quiet sections and a hairline-separated list. No band, as the doc records.
- **Processing Overview, seeded:** clean apart from A1 (the band) and L1 (the caption).
- **Library > Files, Codecs, Languages, Problems.** Consistent quiet tables and sections.
- **Jobs.** A quiet table with pagination. Clean.
- **Libraries, Direct Play devices.** A two-column list, but grid rows stretch, so the
  hairlines line up across both columns. The catalogue has eight devices, so no orphan. It
  would gain one if the catalogue ever became odd.
- **Schedules.** Two identical-shape windows side by side is a comparison layout with equal
  natural heights, not a ragged grid. Clean apart from C3.
- **Settings > Logs, Upgrade (non-Windows), Notifications (list view).** Clean apart from C1.
- **Not found.** Clean.
- **Setup and Login.** A card on a bare background is the right shape for a standalone screen
  outside the workspace. The language governs what sits in a workspace panel.
- **Narrow (390), all 25 screens, both themes.** Single column, no horizontal overflow, and
  stacked bands read correctly.

## Not inspected by eye

The harness cannot open these, because each is behind a click. Reviewed from source only:
the library editor (behind "Edit" or "Add library →") is pairs of like fields with no odd
counts. The Windows-only Upgrade "Update mode" section and the Notifications edit/add forms
were converted (N2, N3) but do not appear in any screenshot.

## Deleted as stranded

`MmOverviewSection`; the `mm-proc-panel__*` and `mm-proc-step*` rules; `.mm-card`,
`.mm-card__title`, `.mm-card__body`, `.mm-dash-card.mm-card`, `.mm-card-action-body`,
`.mm-card-action-footer` and `.mm-module-surface`, with their density overrides; and
`SUITE_SETTINGS_DASH_CARD_CLASS` / `SUITE_SETTINGS_PREMIUM_PANEL_CLASS`. After #613 and
this change, nothing uses a card anywhere in the workspace.

## "In hand" is now "Home"

James renamed the landing screen **Home**. It is not "Dashboard": the 3.0.0 notes say the
Dashboard was removed and `/dashboard` is gone. The route stays `/`. The screen's subject
is unchanged, and it still says so under the heading: files Weir is responsible for right
now, between your media manager handing them over and getting them back.

**Visible text:** the sidebar item and its tooltip, the page heading, "Go to Home" on the
not-found page and the route error screen, the empty section heading ("Nothing held right
now") and the empty band sentence ("Weir is holding nothing right now."). Processing >
Overview's census sentences say "holding" instead of the old name's idiom.

**Identifiers, all renamed:** `pages/in-hand/in-hand-page.tsx` → `pages/home/home-page.tsx`,
`InHandPage` → `HomePage`, `.mm-inhand-*` → `.mm-home-*`, every `data-testid="in-hand-*"` →
`home-*` (only the page's own unit test used them, and every tree was grepped), the
`IN_HAND` status set → `HELD_STATUSES`, the Processing locals `inHand` → `censusTotal`, the
harness slug `04-in-hand` → `04-home`, the live-packaged step `in_hand()` → `home()`, the
e2e test `test_in_hand_is_the_landing_page` → `test_home_is_the_landing_page`, the README
images `screenshots/in-hand*.png` → `home*.png` (recaptured with
`capture-readme-screenshots.py`) and `docs-site/static/img/in-hand.png` → `home.png`.

**Kept on purpose:** ADR-0016's "what is in hand" (an accepted decision record, in plain
English rather than naming the screen); the one-line history note at the top of
`home-page.tsx`; and `redesign-docs-impact.md`, which records the old names as they were
and now carries a note saying what they became.
