# What the content redesign breaks in the docs

An inventory of every documentation asset the [content-language](content-language.md)
redesign makes wrong or stale, plus the product-blurb wording that predates library
mode. Written while several page conversions are still in flight, so it separates what
is wrong *now*, what will become wrong *once a specific PR merges*, and what cannot be
worded correctly until a still-converting screen settles.

**No screenshots were regenerated to produce this document or its fixes.** Every
image below is unchanged; only prose was edited, and only where a sentence was wrong
independent of how an in-flight screen finishes.

As of this writing, against `origin/main`:

| Screen | Status |
| --- | --- |
| Processing Overview | Converted, merged (#588) |
| Setup wizard | Converted, merged (#592) |
| In hand | Converted, merged (#593) |
| Route error screen | Restyled, merged (#590) — not part of the content language, not covered below |
| Activity | Converted, **open PR #596**, not yet merged |
| Processing Library (Overview/Files/Codecs/Languages/Problems) | Uncommitted work in progress, no PR yet (worktree `weir-library-tab`, branch `design/processing-library-tab`) |
| Processing Libraries / Audio & subtitles / Schedules | Uncommitted work in progress, no PR yet (worktree `wt-processing-config`, branch `design/processing-config-tabs`) |
| Processing Files / Jobs / Maintenance | Uncommitted work in progress, no PR yet (worktree `wt-processing-data`, branch `design/processing-data-tabs`) |
| Settings (all tabs) | Uncommitted work in progress, no PR yet (worktree `wt-settings-content`, branch `design/settings-content`) |

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
directory; four of its eight images (`existing-library.png`, `in-hand-light.png`,
`in-hand-mobile.png`, `processing-detail.png`) are unreferenced from any `docs-site`
page — confirmed identical byte-for-byte to their `screenshots/` counterparts, and
dead weight in the Docusaurus build.

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
5. **Cosmetic / cleanup** — the four unreferenced duplicates under
   `docs-site/static/img/` (`existing-library.png`, `in-hand-light.png`,
   `in-hand-mobile.png`, `processing-detail.png`). Not linked from anywhere;
   removing them is safe once the referenced set is refreshed, but it isn't a
   documentation-accuracy problem on its own.

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

- `docs/smoke-checklists.md:21` (Backup and Restore "cards") — reword once
  `design/settings-content` ships and the actual Settings → Backup and restore shape
  is known.
- `docs/visual-identity.md:8` ("Sidebar, cards, surfaces") — re-audit which surfaces
  still use the Slate card treatment once every page in the table in §0 has
  converted; today's answer is a moving target.
- `README.md`'s screenshot gallery captions (`Existing library` → `Library`, and
  whatever remaining pages need renaming) — fold into the screenshot refresh in §4,
  not a standalone text edit, so the caption and the pixels change together.
- `docs/ux-polish.md:30` ("Bubbles, badges, and pills should use the same shape
  language across In hand, Activity, Settings, and Processing.") — this is currently
  *unfulfilled* rather than *false*: In hand already uses the new
  `.mm-quiet-badge`/`.mm-quiet-state` shapes; Activity, Settings and most of
  Processing still use the old ones. The rule itself (aspirational consistency)
  remains correct and needs no rewrite, but is worth re-checking once every page in
  §0 has converted, in case the shapes chosen along the way actually diverged rather
  than merely lagging.

## Needs verification, not guessed

Per the constraint against inventing product behaviour, these are flagged rather than
answered:

- Whether `docs/ux-polish.md:37` ("Processing activity can show before/after file
  details, size savings, languages, subtitles, and removals in an expandable
  layout.") still holds once Processing → Files converts (`wt-processing-config` /
  `wt-processing-data`). The expandable-row behavior it describes is exactly what
  `processing-detail.png` shows today, mid-conversion; I did not change the running
  code, so I can't confirm what the expandable layout will look like once that PR
  lands.
- Whether any other `apps/web` copy still says "Refiner" outside the one screenshot
  found in §1. A `grep -ri refiner apps/web/src` after `wt-processing-data` merges
  would confirm; I did not do a full-repo sweep beyond the file the stale screenshot
  points at, since re-auditing all of `apps/` is out of scope for a docs-only PR.

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

- **`screenshots/processing-detail.png`** ("Processing record detail" — an expanded
  file-history row inside Files). The harness only opens each screen's default state;
  it never clicks a row open. Whoever refreshes this needs a bespoke Playwright step
  (or a manual capture) against the seeded server the harness already knows how to
  start: navigate to `?tab=files`, click a completed file's row to expand its
  history, then screenshot. If the person doing this wants to reuse the harness's own
  plumbing rather than writing new automation, `scripts/screenshot-site.py`'s
  `run_scenario()` and `Shooter` class are the reference — the seeded server startup,
  theme/viewport contexts and login flow are already exactly what a bespoke capture
  needs, only the click-to-expand step and the one-off screenshot call are new. Once
  captured, replace `screenshots/processing-detail.png` and delete the unreferenced
  `docs-site/static/img/processing-detail.png` duplicate rather than update it too.
- **Confirming `processing-detail.png` no longer says "Refiner" anywhere.** Read the
  new capture, not just the class names, since this is exactly the kind of leftover
  string a purely structural review would miss.

### Cleanup once the refresh lands

Delete the four unreferenced duplicates under `docs-site/static/img/` instead of
refreshing them, unless a future PR starts referencing them from a `docs-site` page:

```powershell
git rm docs-site/static/img/existing-library.png
git rm docs-site/static/img/in-hand-light.png
git rm docs-site/static/img/in-hand-mobile.png
git rm docs-site/static/img/processing-detail.png
```

(`docs-site/static/img/in-hand.png` and `docs-site/static/img/processing.png` stay —
`docs-site/src/pages/index.tsx` references both.)
