# What the content redesign breaks in the docs

An inventory of every documentation asset the [content-language](content-language.md)
redesign makes wrong or stale, plus the product-blurb wording that predates library
mode. Written while several page conversions are still in flight, so it separates what
is wrong *now*, what will become wrong *once a specific PR merges*, and what cannot be
worded correctly until a still-converting screen settles.

**No screenshots were regenerated to produce this document or its fixes.** Every
image below is unchanged; only prose was edited, and only where a sentence was wrong
independent of how an in-flight screen finishes.

> **Since written:** the main screen this document calls "In hand" was renamed **Home** in
> #614, and its files moved with it: `screenshots/in-hand*.png` are now `screenshots/home*.png`,
> `docs-site/static/img/in-hand.png` is `home.png`, `pages/in-hand/in-hand-page.tsx` is
> `pages/home/home-page.tsx`, `mm-inhand-*` is `mm-home-*`, and the harness slug `04-in-hand`
> is `04-home`. The inventory below is left as it was written, as a record of what it found.

> **Update (2026-09-18): every conversion in the table below has now merged**, and the items this
> document deferred to "once a shipped screen settles" have been worked through — see
> [Deferred](#deferred--needs-a-shipped-screen-to-word-correctly) and
> [Needs verification](#needs-verification-not-guessed), both now closed out with what was found. The
> screenshot refresh in §4 is the one part still outstanding; it is in flight separately, so §1 and §4
> are left exactly as written.

As of this writing, against `origin/main`:

| Screen | Status |
| --- | --- |
| Processing Overview | Converted, merged (#588) |
| Setup wizard | Converted, merged (#592) |
| In hand | Converted, merged (#593) |
| Route error screen | Restyled, merged (#590) — not part of the content language, not covered below |
| Activity | Converted, ~~open PR #596~~ **merged (#596)** |
| Processing Library (Overview/Files/Codecs/Languages/Problems) | ~~Uncommitted work in progress~~ **Converted, merged (#597)** |
| Processing Libraries / Audio & subtitles / Schedules | ~~Uncommitted work in progress~~ **Converted, merged (#601)** |
| Processing Files / Jobs / Maintenance | ~~Uncommitted work in progress~~ **Converted, merged (#600)** |
| Settings (all tabs) | ~~Uncommitted work in progress~~ **Converted, merged (#599)** — applied sparingly; the action cards in Backup and restore were deliberately left alone |

> **Status note, 2026-09-18.** Every row above except Settings has since merged
> (#596, #597, #600, #601). Settings did not: the owner rejected the converted result,
> and Settings → General is being rebuilt on `design/settings-general-content`. A
> design-QA pass (`design/site-qa`) is running across the other screens for the same
> class of defect — ragged multi-column grids, an orphaned card in a last row, bordered
> things nested inside bordered things, cards a conversion missed, and pages that
> disagree with each other. ~~**So the reshoot in §4 is on hold**~~ **Done: the README
> screenshot refresh landed on `main` with the 3.0.0 release (#583), and `library.png` was
> re-shot again in #615 after its problem-count and "(s)" copy fixes.** As first written:
> `processing.png` and
> `settings.png` are near-certain to change again, and anything captured before that
> pass settles would be obsolete within the hour. Re-read this document before shooting;
> the layouts will have moved.

Separately, a recent PR changed the sidebar's product blurb from "Cleans every download
before your media manager imports it" to "Cleans new downloads, and files already in
your library" (`apps/web/src/components/brand/brand-header-link.tsx:20` and
`apps/web/src/components/brand/auth-brand-stack.tsx:14`), because the old sentence
predates library mode. That sentence is baked as pixels into every screenshot in this
repo (see below), and one copy of an equivalent sentence was still live in prose.

---

## 1. Screenshot inventory

Two locations hold screenshots: the repo-root `screenshots/` directory (linked from
`README.md`) and `docs-site/static/img/` (linked from `docs-site/src/pages/index.tsx`).
There is no `docs/screenshots/` — `README.md`'s relative links resolve against the
repo root. `docs-site/` has no screenshots of its own beyond that `static/img/`
directory; **six** of its eight images (`activity.png`, `existing-library.png`,
`in-hand-light.png`, `in-hand-mobile.png`, `processing-detail.png`, `settings.png`) are
unreferenced from any `docs-site` page — confirmed identical byte-for-byte to their
`screenshots/` counterparts, and dead weight in the Docusaurus build.

> **Corrected 2026-09-18.** This paragraph first said four. All eight are byte-identical
> duplicates, and `docs-site` references exactly two of them: `processing.png`
> (`src/pages/index.tsx:14`) and `in-hand.png` (`src/pages/index.tsx:88`). `activity.png`
> and `settings.png` are as unreferenced as the other four. All six have now been deleted.

All eight images were last touched in the same commit, `b921284a` ("docs: new
screenshots and page names for the Weir design, closes #564", #569). That commit
landed **before** the content-language redesign started (#588 and everything after
it), so every image predates rule 1, rule 2 and rule 3 as described in
`content-language.md`, and all of them still show the sidebar's old blurb.

| File | Screen shown (harness screen #) | Conversion status | Severity |
| --- | --- | --- | --- |
| `screenshots/in-hand.png` | In hand, dark, desktop (`04-in-hand`) | **Converted, merged** (#593) | Flatly false — structure literally changed |
| `screenshots/in-hand-light.png` | In hand, light, desktop (`04-in-hand`) | Converted, merged (#593) | Flatly false |
| `screenshots/in-hand-mobile.png` | In hand, dark, narrow/phone (`04-in-hand`) | Converted, merged (#593) | Flatly false |
| `screenshots/processing.png` / `docs-site/static/img/processing.png` | Processing → Overview, dark, desktop (`06-processing-overview`) | **Converted, merged** (#588) | Flatly false |
| `screenshots/activity.png` | Activity, dark, desktop (`05-activity`) | **Converting, open PR #596** | Stale, about to become flatly false |
| `screenshots/existing-library.png` | Processing → Library → Overview, dark, desktop (`11-processing-library-overview`) — specifically the folders/schedule/dedup panel (`LibrarySettingsPanel`) stacked under the overview | **In progress, uncommitted** (`weir-library-tab`) | Stale now (tab is captioned "Existing library"; the tab was renamed to "Library" in #568, unrelated to this redesign), will also become structurally false once the library tab converts |
| `screenshots/settings.png` | Settings → General, dark, desktop (`18-settings`) | **In progress, uncommitted** (`wt-settings-content`) | Stale now, will become structurally false on merge |
| `screenshots/processing-detail.png` | Processing → Files, an expanded file-history row (within `10-processing-files`) | **In progress, uncommitted** (`wt-processing-data`) | Doubly wrong: the row still prints "REFINER WATCHED FOLDER RESOLVED" — leftover from before the product dropped the Refiner name (#563/#567) — and it will also change shape once Files converts |

Sort by how wrong each is:

1. **Flatly false today** — `in-hand.png`, `in-hand-light.png`, `in-hand-mobile.png`,
   `processing.png`. The pages they show have already shipped the redesign: no more
   equal-width three- or five-box rows, no bordered library cards. `in-hand.png` and
   `processing.png` both show the exact "five identical boxes of equal weight" and
   "three equal boxes" patterns `content-language.md` calls out by name as the thing
   the redesign replaces.
2. **Flatly false on an unrelated, older axis, and about to be false on this one too**
   — `existing-library.png`. Its caption and its own tab-strip pixels both say
   "Existing library," a name the product retired in #568. Once
   `design/processing-library-tab` lands, the panel underneath will also lose its
   cards.
3. **Contains dead product terminology** — `processing-detail.png`. "Refiner" has not
   been a user-visible string since #563/#567; this row is the one place in the whole
   documentation set where it still appears, and it will be replaced by a converted
   Files row on top of that.
4. **Stale, soon flatly false** — `activity.png`, `settings.png`. Structurally still
   close to what's on `main` today (mid-air, since neither has merged), but both will
   be wrong the moment their PR lands, and both already carry the old sidebar blurb.
5. **Cosmetic / cleanup** — the six unreferenced duplicates under
   `docs-site/static/img/` (`activity.png`, `existing-library.png`, `in-hand-light.png`,
   `in-hand-mobile.png`, `processing-detail.png`, `settings.png`). Not linked from
   anywhere; removing them did not have to wait for the refreshed set, and it isn't a
   documentation-accuracy problem on its own. **Done.**

Every one of the eight images additionally shows the sidebar's old blurb, "Cleans
every download before your media manager imports it" — see the background section
above.

## 2. Prose describing page layout or UI structure

| Location | Quote | Wrongness | Disposition |
| --- | --- | --- | --- |
| `docs/design/content-language.md:27` (before this PR) | "Activity \| What has happened in the window being viewed, by outcome" | Flatly false: Activity shipped (#596) with no band at all | **Fixed in this PR** — see below |
| `docs/design/content-language.md:26` (before this PR) | "In hand \| Where the files in hand are sitting right now" | Not wrong, but under-specified next to what shipped (six named statuses, not three) | **Fixed in this PR** — tightened, not corrected |
| `docs/ux-polish.md:14-16` | "Cards in the same section should use consistent spacing... Settings cards should be grouped by user task..." | Directly contradicted by content-language.md rule 3 ("No cards, no panels, no wells" below the lead) for every page once it converts. True today only for the pages still unconverted (Settings, Processing's non-Overview tabs) | **Fixed in this PR** — added a supersession note; did not delete the bullets, since dialogs and the frozen shell may still use card-shaped chrome |
| `docs/smoke-checklists.md:20` | "confirm setup wizard, timezone, log retention, and display density **cards** render correctly" | Flatly false for the setup wizard specifically — it lost its card in #592. Still true for timezone/log retention/display density, which live in Settings General and have not converted | **Fixed in this PR** — split the setup-wizard clause out |
| `docs/smoke-checklists.md:21` | "Confirm Backup and Restore controls sit consistently at the bottom of their **cards**." | True today (Settings → Backup and restore hasn't converted); will be false once `design/settings-content` merges, since the final shape of that tab isn't settled | **Deferred** — needs the shipped Settings redesign to reword accurately |
| `docs/visual-identity.md:8` | "Slate `#1F232A` \| Sidebar, cards, surfaces" | Ambiguous rather than false: Slate still colors the frozen sidebar and still appears in dialogs and figure tiles, just not most page bodies any more | **Deferred / needs verification** — rewording this confidently requires knowing which surfaces still use Slate once every page converts; listing rather than guessing |
| `README.md:31,35,39,43,49` (screenshot captions) | "Existing library" caption over `existing-library.png` | The tab was renamed to "Library" in #568 | **Deferred** — see note below: fixing the caption without fixing the image it sits above would make the mismatch worse, since the screenshot itself has "Existing library" printed in its tab strip. Bundle this with the screenshot refresh, not this PR. |

I did not find the literal old product blurb ("Cleans every download before your media
manager imports it") anywhere in `docs/` or `docs-site/docs/` prose — only baked into
the screenshots (§1) and, until this PR, in one piece of website copy (§3).

I did not find `document.documentElement.scrollWidth === document.documentElement.clientWidth`
or any other horizontal-overflow check written down anywhere in `docs/` or
`README.md`. If one exists, it is not in this repository's documentation.

## 3. Product purpose described in pre-library-mode terms

| Location | Before | After |
| --- | --- | --- |
| `docs-site/src/pages/index.tsx:12-13` (Processing feature card description) | "Keep the audio and subtitle tracks you want **in each download** and remove the rest, library by library, with configurable worker lanes." — silent on library mode, same omission the sidebar blurb had | **Fixed in this PR**: "Cleans new downloads, and files already in your library: keep the audio and subtitle tracks you want and remove the rest, library by library, with configurable worker lanes." |

`README.md`'s own "What Weir is" section already mentions library mode ("...and can
also clean files already sitting in an existing library") and needed no change.
`docs-site/src/pages/index.tsx:88`'s "In hand, at a glance" caption already matches
the current `mm-page__lead` text in `apps/web/src/pages/in-hand/in-hand-page.tsx`
verbatim and needed no change either — only the image beneath it (`in-hand.png`) is
stale.

---

## Fixes applied in this PR

1. **`docs/design/content-language.md`** — corrected the rule-1 table:
   - Activity now reads "No band. Shipped without one — see below," with a new
     paragraph explaining *why*: not because outcome counts are unobtainable
     (`result` is a real, exact-match, server-side-filterable column on
     `GET /api/v1/activity/recent`, and that endpoint's `total` is a genuine
     whole-filtered-set count, so six calls would give six honest,
     pagination-proof segment counts) but because of **cost** —
     `useActivityStreamInvalidation` invalidates the whole `["activity", "recent"]`
     query-key prefix on every SSE activity event, so six always-mounted count
     queries would be a 7x refetch amplification during a processing run.
   - In hand's row now says "The six statuses of the pool Weir is holding, left to
     right, each a filter into Files," matching what shipped
     (`apps/web/src/pages/in-hand/in-hand-page.tsx`'s `HOLDING_STAGES`) rather than a
     vaguer description that could be misread as the three-box strip the old design
     used.
2. **`docs/ux-polish.md`** — added a supersession note above the Layout section's
   card-related bullets, pointing at `content-language.md` as the tie-breaker for
   page bodies, and explaining which surfaces (frozen shell, dialogs) the old bullets
   still legitimately describe.
3. **`docs/smoke-checklists.md`** — split the Windows smoke checklist's setup-wizard
   card claim out from the still-accurate timezone/log-retention/display-density
   card claims, since only the former is wrong today.
4. **`docs-site/src/pages/index.tsx`** — reworded the Processing feature description
   to state library mode, mirroring the sidebar's already-corrected blurb.
5. **`docs/README.md`** — added a link to this document under Product And UX Rules.

I looked for, and did not change, anything under `apps/`.

## Deferred — needs a shipped screen to word correctly

**All four resolved (2026-09-18), now that every conversion in §0 has merged.** What each turned out to be:

- `docs/smoke-checklists.md:21` (Backup and Restore "cards") — **still true, no reword needed.**
  #599 applied the content language to Settings sparingly and left the action cards in Backup and
  restore alone; `apps/web/src/pages/settings/settings-backup-tab.tsx` still renders them with
  `mm-card-action-body` / `mm-card-action-footer`, so the controls do sit at the bottom of their
  cards. The checklist step now says so, and says why, rather than reading as an unreviewed leftover.
- `docs/visual-identity.md:8` ("Sidebar, cards, surfaces") — **re-audited, and the whole page needed
  more than that one row.** Every hex in the palette table was from the pre-Tailrace one-pager and
  none of them matched `weir-tokens.css` after #570 re-themed the app (charcoal-and-warm-gold →
  cool slate and teal-cyan), and the "dedicated WebP mark with a 20 KiB budget" delivery rule
  predated #581/#582/#587 replacing the image with an inline SVG. Both are corrected, with Slate's
  narrowed scope written down as this item asked.
- `README.md`'s screenshot gallery captions — **still deferred, deliberately.** Unchanged for the
  reason originally given: the caption and the pixels have to move together, and the screenshot
  refresh is in flight separately.
- `docs/ux-polish.md:30` (badge shape language) — **diverged, not merely lagging.** There are three
  shape families on `main` now: `mm-inhand-row__state` (In hand), `mm-activity-chip` /
  `mm-status-badge` (Activity), and `mm-quiet-badge` / `mm-quiet-state` (Processing and Settings).
  In hand did *not* end up on the new shapes as this document expected. The rule is left as the
  target and annotated with the real state, since closing it is now a consolidation someone has to
  choose to do.

## Needs verification, not guessed

Per the constraint against inventing product behaviour, these are flagged rather than
answered:

**Both answered (2026-09-18), against merged `main`.**

- `docs/ux-polish.md:37` ("Processing activity can show before/after file details, size savings,
  languages, subtitles, and removals in an expandable layout") — **still holds after #600.** The
  detail survived the conversion as the expandable **Processing record** entry in a file's history in
  `processing-files-section.tsx`, which labels source and output file and size, space saved, net
  space saved, the processing plan, output validation, source cleanup and duration, with the raw
  payload behind a nested `<details>`. It is an expandable row rather than a card now; the behaviour
  the bullet asks for is unchanged. The bullet is annotated rather than rewritten.
- Whether any other `apps/web` copy still says "Refiner" — **no.** A full-repo
  `grep -ri refiner` finds it in exactly three kinds of place, none of them user-visible:
  historical SQL migration *filenames* in `SchemaMigrator.cs` (identifiers of migrations that already
  ran, which cannot be renamed without breaking upgrades), the migration tests that exercise those
  old table names, and two comments in `router.tsx` and `processing-page.test.tsx` that exist
  precisely to keep the name from coming back. `processing-page.test.tsx` asserts no rendered text
  matches `/Refiner/`. The only remaining live appearance is the one baked into
  `screenshots/processing-detail.png`, as §1 says.

---

## 4. Screenshot refresh plan

Run this **after** the four in-flight conversions (`design/activity-content`,
`design/processing-library-tab`, `design/processing-config-tabs`,
`design/processing-data-tabs`, `design/settings-content`) have all merged to `main` —
not before, or the new screenshots will be stale within the hour, same as the ones
this document describes.

### What the harness covers

`scripts/screenshot-site.py` captures all 19 screens (`GATED_SCREENS` +
`NORMAL_SCREENS` in that file), in both themes (`dark`, `light`) and both widths
(`desktop` 1440×1000, `narrow` 390×844), twice — once against an empty install, once
seeded with representative data — and writes
`<index>-<slug>--<empty|seeded>--<theme>--<desktop|narrow>.png` plus a
`contact-sheet.html` and `manifest.txt`.

`seed_representative_data()` was extended while preparing the refresh: Processing →
Overview's "last 30 days" figures are not read off the activity rows' text but by
re-parsing the detail of `processing.file_remux_pass_completed` events as the JSON
envelope `RemuxPassHandler` writes (`OverviewStatsStore.BuildAsync`). The seed's two
finished passes were plain `job_completed` lines, so they appeared in the feed and in
none of the figures, and a fully seeded install reported **0 files handed back and a 0%
success rate** directly beside a band saying it had handed back two. Both now carry the
real event type and the real envelope.

From the repository root, one time, before running it:

```powershell
cd apps\web
npm ci
npm run build
cd ..\..
dotnet build apps\server\src\Weir.Host
python -m playwright install chromium   # once per machine
```

Then, from the repository root:

```powershell
python scripts/screenshot-site.py .\screenshot-refresh
```

> **Verified 2026-09-18, and this is no longer the right command for the README.**
> The screen numbering and slugs below still match `scripts/screenshot-site.py` on
> `main` (`04-in-hand`, `05-activity`, `06-processing-overview`,
> `11-processing-library-overview`, `18-settings`) — the five conversions that have
> landed since did not renumber anything. What does not match is the **frame**. The
> harness shoots `full_page=True` at `device_scale_factor=2`, from a 1440×1000 desktop
> viewport and a 390×844 narrow one. Every image this repo publishes is viewport-only
> at `device_scale_factor=1`, 1440×900 on the desktop and 400×860 on the phone (read
> straight out of the PNG headers). Publishing a harness frame would change the size of
> every image in the README gallery and reflow it.
>
> So the README's set is now captured by
> [`scripts/capture-readme-screenshots.py`](../../scripts/capture-readme-screenshots.py),
> which imports the harness and reuses its bring-up wholesale — the disposable
> `WEIR_HOME`, the server process, `seed_representative_data()`, the theme mechanism and
> the throwaway admin bootstrapped over the API — and replaces only the viewport, the
> device scale factor, and the list of shots. It captures all eight published images,
> including the processing record below, in one pass:
>
> ```powershell
> python scripts/capture-readme-screenshots.py .
eadme-shots
> ```
>
> The harness stays exactly what it is for: reviewing every screen, both themes, both
> widths, empty and seeded. Use it for that, and the table below to know which harness
> frame corresponds to which published image.

That produces every frame this document's screenshots need. The mapping from the
harness's output to the seven images this repo actually publishes:

| Publish as | Take from |
| --- | --- |
| `screenshots/in-hand.png` (and the identical `docs-site/static/img/in-hand.png`) | `screenshot-refresh/04-in-hand--seeded--dark--desktop.png` |
| `screenshots/in-hand-light.png` | `screenshot-refresh/04-in-hand--seeded--light--desktop.png` |
| `screenshots/in-hand-mobile.png` | `screenshot-refresh/04-in-hand--seeded--dark--narrow.png` |
| `screenshots/activity.png` (and `docs-site/static/img/activity.png` if it starts being referenced) | `screenshot-refresh/05-activity--seeded--dark--desktop.png` |
| `screenshots/processing.png` (and `docs-site/static/img/processing.png`) | `screenshot-refresh/06-processing-overview--seeded--dark--desktop.png` |
| `screenshots/existing-library.png` → **rename to `screenshots/library.png`** and update `README.md`'s caption from "Existing library" to "Library" in the same commit | `screenshot-refresh/11-processing-library-overview--seeded--dark--desktop.png` |
| `screenshots/settings.png` | `screenshot-refresh/18-settings--seeded--dark--desktop.png` |

Use the `seeded` scenario for all of the above — every one of today's screenshots
shows non-empty data (files in hand, processed counts, activity rows, a configured
library), and the harness's `empty` pass exists for reviewing empty states, not for
the README gallery.

### What the harness cannot give you

- **`screenshots/processing-detail.png`** ("Processing record detail"). The harness
  only opens each screen's default state; it never presses a button. This panel is
  behind **Processing record** on a file's row in Processing → Files
  (`processing-file-log-{id}` opens `processing-file-log-panel`) — not an expanded
  history row, which is what this document assumed before the Files conversion landed.
  `scripts/capture-readme-screenshots.py` now drives it.
- **A processing record to open.** `seed_representative_data()` seeds files, jobs,
  library rows and activity, but no `file_logs` rows at all, so the panel opens saying
  "0 record(s)" against an otherwise well-seeded install. The capture script seeds one
  `file_logs` row for the file the harness already marks `processed`, shaped like the
  payload `RemuxPassRunner` writes for a successful live remux, and fails the run rather
  than shoot an empty panel.
- **Confirming `processing-detail.png` no longer says "Refiner" anywhere.** Read the
  new capture, not just the class names, since this is exactly the kind of leftover
  string a purely structural review would miss. For what it is worth, the source is
  already clean: the only `refiner` left in `apps/web/src` is a legacy route redirect
  and two regression tests that assert the name is absent. The stale pixels came from
  the record's own stored JSON key, `refiner_watched_folder_resolved`, which migration
  `0009_drop_the_refiner_name.sql` renamed to `processing_watched_folder_resolved`; a
  record written by today's server cannot carry the old spelling.

### Cleanup once the refresh lands

Delete the four unreferenced duplicates under `docs-site/static/img/` instead of
refreshing them, unless a future PR starts referencing them from a `docs-site` page:

**Done** — all six unreferenced duplicates were removed ahead of the reshoot, since
nothing referenced them and nothing about the redesign changes that:

```powershell
git rm docs-site/static/img/activity.png
git rm docs-site/static/img/existing-library.png
git rm docs-site/static/img/in-hand-light.png
git rm docs-site/static/img/in-hand-mobile.png
git rm docs-site/static/img/processing-detail.png
git rm docs-site/static/img/settings.png
```

(`docs-site/static/img/in-hand.png` and `docs-site/static/img/processing.png` stay —
`docs-site/src/pages/index.tsx` references both.)
