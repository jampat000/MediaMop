# The Weir content language

How the *content* of every Weir page is laid out. The shell around it — sidebar, top
bar, page header, workspace tab row — is finished and frozen; this document is only
about what sits inside a workspace panel.

The reference implementation is the Processing **Overview** tab
(`apps/web/src/pages/processing/processing-overview-tab.tsx`). The primitives it uses
are page-neutral and live in `apps/web/src/styles/weir-content.css`. Read this page,
then read that component, then convert your page.

---

## The three rules, in priority order

### 1. The page leads with what is happening now, as a band across the top

Not a grid of cards. One bordered band, full width, whose segments are as wide as the
number each carries — and where it is too narrow for that, a labelled list of the same
stages rather than a lie about their sizes. Each segment is a control that opens the
detail behind it.

**The band's caption must stay true at every width.** "Each stage is as wide as the
number of files in it" was in both captions and is false the moment the band restacks;
say what a segment *does* ("Click a stage to open Files filtered to it") instead.

The band answers the first question a page exists to answer:

| Page              | The band is                                                             |
| ----------------- | ----------------------------------------------------------------------- |
| Processing        | The pipeline: six file statuses, left to right, each a filter into Files |
| In hand           | The six statuses of the pool Weir is holding, left to right, each a filter into Files |
| Activity          | No band. Shipped without one — see below                                 |
| Settings          | No band. Settings has no "now" — it starts at rule 3                     |

If you cannot name a "now" for your page, **do not invent one.** A page with no band
starts at rule 3 and that is a correct outcome, not a shortcut.

**Why Activity has no band.** This table once pencilled Activity in as "by outcome," and
that turned out to be unbuildable as written (#596). The reason is not that outcome
counts are unobtainable: `result` is a real stored column and an exact-match
server-side filter on `GET /api/v1/activity/recent` already, and that endpoint's
`total` is a genuine count over the whole filtered set — not just the page loaded — so
six calls to it would give six honest, pagination-proof segment counts. It was
rejected on **cost**. Activity is SSE-driven: `useActivityStreamInvalidation`
invalidates the whole `["activity", "recent"]` query-key prefix on every activity
event, so six always-mounted count queries would turn into a 7x refetch amplification
on every event during a processing run. If that cost is ever paid down (a dedicated
counts endpoint, a cheaper invalidation scope), a band becomes buildable again — but
build it against that endpoint, not by aggregating the currently loaded page of rows
client-side the way row tone is computed today, which would misrepresent itself the
moment anyone pages.

The band is the one place a page is allowed to be visually loud: a border, a filled
surface, a 3px accent rule along the top of each segment, a 30px number. Nothing else
on the page gets any of that.

### 2. One hero, then quiet

Where a page has a number that actually carries it, that number gets a wide tile and
its supporting numbers get narrow tiles beside it, in one row of unequal widths.

- The hero is the number someone would quote if asked how the thing is going. On
  Processing that is files processed in the last 30 days.
- Supporters qualify the hero. On Processing: success rate, and space reclaimed.
- Two or three supporters. Not four.

**Five identical boxes of equal weight is the thing this replaces.** If every tile on
your row is the same width, you have not applied this rule.

If the page has no single number worth that much room, skip the figure row entirely
and go to rule 3. An invented hero is worse than no hero.

### 3. Everything below the lead is borderless

No cards, no panels, no wells. Hierarchy comes from type scale and whitespace: a
section heading, a hairline, then content.

- A section is a heading on the left, its links on the right, a hairline under both,
  then the content.
- The only control the quiet body carries is a text link (`Open Libraries →`). Not a
  button with chrome.
- Tables lose their box. The header row is uppercase eyebrow type over a `--mm-line`
  hairline; body rows are separated by a fainter `--mm-border` hairline; the last row
  has none. (The mockup James approved keeps the per-row hairlines — that is the
  authority here, over any shorter description of this rule.)

This is where most of a page lives, and it should be the quietest part of it.

---

## A Tailwind utility cannot override a `weir-*.css` class

This one has cost several people an afternoon, so read it before you debug a style that
"does nothing".

`apps/web/src/index.css` starts with `@import "tailwindcss"`, and Tailwind v4 emits every
utility inside `@layer utilities`. The `weir-*.css` files are imported after it and are
**unlayered**. Cascade layers are resolved *before* specificity, and an unlayered
declaration outranks a declaration in any layer — so a Tailwind utility on an element that
also carries a `weir-*` class simply never applies to a property that class sets, and does
so silently. This is why a `min-w-[7.25rem]` on a `.mm-lead-band__segment` did nothing.

Measured against the built stylesheet: the rule for `.mm-quiet-stack` is unlayered and the
rule for `.min-w-0` is in `utilities`. On a bare element, `.block` computes `display:
block` and `.mm-quiet-stack` computes `display: flex`; on an element carrying **both**, it
computes `flex`.

Three things follow, and the third is the one to reach for:

- **Adding specificity does not help.** The layer decides it first. `.a .block` still loses.
- **Reordering the imports does not help either.** It is layering, not source order.
- **The property belongs in the `weir-*` class.** If a page needs a different value, the
  primitive is either missing a modifier or being used for something it is not. Add the
  modifier here. Tailwind's `!` suffix (`block!`) does win, because an important
  declaration beats a normal one whatever the layers — but reaching for it means the
  primitive and the page disagree, and the next person cannot see that from the markup.

Utilities are still fine for anything no `weir-*` class touches — `min-w-0` on a plain
`div`, the layout inside a table cell, spacing between two `.mm-quiet-link`s. The trap is
only the overlap.

---

## Two standing rules that override the three above

### The chrome is frozen

Do not touch, in markup or in styles:

- `apps/web/src/components/shell/**` — sidebar, top bar
- `apps/web/src/components/shared/workspace-shell.tsx` — `WorkspacePage`,
  `WorkspacePanel`, `WorkspaceTabList`, and the page header and tab row they render
- Anything in `weir-shell.css` that styles the above

If a layout you want needs a change in there, **you do not do that layout.** Change
what is inside the panel instead. James: "I love the menus side and top."

### The empty state still takes over

A band of six zeroes on a fresh install looks broken. Whatever the page already does
when it has nothing must keep happening, ahead of the band and the figure row.

Processing has two distinct empties, and both are decided, not judged:

| Condition                                | What renders                                                                      |
| ---------------------------------------- | --------------------------------------------------------------------------------- |
| No library has a watched folder          | The existing "Get started" checklist, alone. No band, no figures.                   |
| Folders set, but nothing in hand at all  | One `.mm-quiet-note` sentence where the band would be. The figure row still renders. |
| Census still loading, or failed to load  | The same `.mm-quiet-note` slot, with the loading or failure sentence.                |

Apply the same shape to your page: the strongest empty wins outright; a merely-zero
lead becomes a sentence, not a row of zeroes.

---

## The primitives

All of them are in `apps/web/src/styles/weir-content.css`. Use these; do not write
page-specific layout CSS unless the page genuinely needs something none of these do,
and if it does, add it here as another page-neutral primitive.

### Tokens

Two new custom properties, both layout-only, both defined in `weir-tokens.css`. No
colour and no font was added, and none may be.

| Token               | Default | Set where                       | For                                                     |
| ------------------- | ------- | ------------------------------- | ------------------------------------------------------- |
| `--mm-flow-share`   | `1`     | Inline, per band segment        | That segment's share of the band's width (unitless)      |
| `--mm-meter-fill`   | `0%`    | Inline, per `.mm-figure__meter` | How full the bar is                                      |
| `--mm-band-stacked` | `0`     | `weir-content.css` only         | `1` once the band has restacked. Every difference between a row and a stack is a calc on it, so the band has one switch instead of a rule per segment count. **Never set this from a page.** |

Everything else is an existing `--mm-*` token. `apps/web/scripts/check-design-tokens.mjs`
fails the build on any `var(--mm-…)` that `weir-tokens.css` does not define, so a new
token means a line in that file and a reason beside it.

### Rule 1 — the lead

| Class                            | Element                  | For                                                         |
| -------------------------------- | ------------------------ | ----------------------------------------------------------- |
| `.mm-lead`                       | `div`                    | Wraps the whole lead: interrupts, band, caption, figure row   |
| `.mm-lead-band`                  | `div`                    | The band. One proportional row, or a stacked list — by itself |
| `.mm-lead-band__segment`         | `button`                 | One segment. Set `--mm-flow-share` inline                     |
| `.mm-lead-band__segment--empty`  | modifier                 | Count is zero: grey rule, dimmed value                        |
| `.mm-lead-band__segment--live`   | modifier                 | Something is happening here now: accent rule and value        |
| `.mm-lead-band__label`           | `span`                   | The stage name, uppercase eyebrow                             |
| `.mm-lead-band__value`           | `span`                   | The count                                                     |
| `.mm-lead-band__hint`            | `span`                   | One short line saying what the stage means                    |
| `.mm-lead-band__go`              | `span`, `aria-hidden`    | "Filter →", revealed on hover and keyboard focus              |
| `.mm-lead-band__pulse`           | `i`, `aria-hidden`       | The live dot. Honours `prefers-reduced-motion`                |
| `.mm-lead-caption`               | `p`                      | One line under the band: meaning on the left, the takeaway sentence on the right |

The segment must be a real `<button>` (or `<a>`), never a `div` with `onClick`: the
focus ring, the `→` reveal and keyboard use all hang off that.

**Weighting.** Share is the raw count, floored at 6% of the band's total so an empty
stage still reads as a stage:
`share = total === 0 ? 1 : Math.max(count, total * 0.06)`. Reuse that formula.

**The band never wraps, and a page never says anything about that.** Rule 1 only means
something if a wider segment always carries a bigger number, so the primitive has two
states and both keep that promise:

| State     | When                                                      | What it is                                                                       |
| --------- | --------------------------------------------------------- | -------------------------------------------------------------------------------- |
| **Row**   | The band can give every segment `6rem`                     | One line. Width is share of the total, floored at `6rem`. Both the proportional part and the floor rise with the count, so a bigger number can never draw narrower. |
| **Stack** | It cannot                                                  | A labelled list, one segment per line, the way `.mm-quiet-table` restacks below 760px. Width stops encoding magnitude rather than encoding it wrongly; the number is read directly. |

It is decided from the band's own width against how many segments it holds — a
container query on the band and a `:has()` ladder in `weir-content.css` — so it follows
the *panel*, not the window, and is right with the sidebar at either size. Before it
gives up the row a segment near the floor drops its `.mm-lead-band__hint`, from its own
container query. A page sets `--mm-flow-share` and nothing else.

**This is why a page must not set a segment's `min-width`.** The floor and the ladder
are one number, and raising the floor on one page puts the two out of step: the ladder
keeps the band in a row at a width where the floors no longer fit on one line, it wraps,
and a wrapped band compares widths only *within* a row — which is the bug this design
exists to prevent. Measured on Files with nine segments and a `6.75rem` inline floor: the
band wrapped at every width from 1320 to 1390. If a page's labels genuinely need more
room than the floor gives them, shorten the labels or carry fewer segments.

Before this, `.mm-lead-band` was a wrapping flex row. A flex line justifies itself
independently of every other line, so a count of 1 alone on the second line drew wider
than a count of 2 sharing the first. Swept 390–1600 in 10px steps, Processing Overview
inverted the comparison at 63 of 122 widths with six segments and counts of only 0, 1
and 2; In hand at 3 of 122; Files put its ninth segment on a line by itself at 1280 and
drew a 1 nine times wider than a 2.

**Honesty.** If the band draws a fixed set of states and the data has others, count
them and say so in the caption ("5 more in states the band does not show"). Do not
silently drop them, and do not point two segments at the same filter.

### Rule 2 — the figure row

| Class                     | Element  | For                                                                |
| ------------------------- | -------- | ------------------------------------------------------------------ |
| `.mm-figure-row`          | `div`    | The grid. **First child is the hero at 1.8fr; every later child is 1fr.** No modifier needed for the widths |
| `.mm-figure`              | `section`| One tile                                                           |
| `.mm-figure--hero`        | modifier | Puts the big type on the hero's value. Only on the first child      |
| `.mm-figure--warn`        | modifier | The value is a bad number; paints it `--mm-status-failed-text`      |
| `.mm-figure__eyebrow`     | `div`    | Label on the left, optional context on the right                    |
| `.mm-figure__value`       | `div`    | The number                                                          |
| `.mm-figure__unit`        | `span`   | The words on the hero number's baseline ("files handed back")        |
| `.mm-figure__note`        | `p`      | One sentence under the value                                        |
| `.mm-figure__meter`       | `div`, `aria-hidden` | Percentage bar. Set `--mm-meter-fill` inline           |
| `.mm-figure__foot`        | `div`    | Two or three smaller figures along the bottom of the hero tile       |
| `.mm-figure__foot-value`  | `span`   | One of those numbers                                                |
| `.mm-figure__foot-label`  | `span`   | Its uppercase label                                                 |

At ≤1280px the hero spans the full width with the supporters in two columns beneath;
at ≤720px everything stacks. That happens by itself — do not add breakpoints.

### Rule 3 — the quiet body

| Class                        | Element   | For                                                       |
| ---------------------------- | --------- | --------------------------------------------------------- |
| `.mm-quiet-stack`            | `div`     | The page body. Vertical rhythm between the lead and each section |
| `.mm-quiet-section`          | `section` | One borderless section                                    |
| `.mm-quiet-section__head`    | `div`     | Heading row with the hairline under it                    |
| `.mm-quiet-section__title`   | `h2`      | The heading. Give it an id and `aria-labelledby` the section |
| `.mm-quiet-section__aside`   | `div`     | The section's links, baseline-aligned with the heading    |
| `.mm-quiet-section__body`    | `div`     | The content under the hairline                            |
| `.mm-quiet-link`             | `button` / `a` | The only control shape in the quiet body. Write the label with a trailing `→` |
| `.mm-quiet-note`             | `p`       | A muted paragraph: empty states, captions, explanations   |
| `.mm-quiet-table-wrap`       | `div`     | Horizontal scroll container                               |
| `.mm-quiet-table`            | `table`   | The borderless table                                      |
| `.mm-quiet-table__name`      | `th[scope=row]` | The row's name cell                                 |
| `.mm-quiet-table__strong`    | `span`    | A primary value inside a cell                             |
| `.mm-quiet-table__sub`       | `span`    | The explanatory line under it                             |
| `.mm-quiet-badge` / `--off`  | `span`    | A small pill beside a name                                |
| `.mm-quiet-state` / `--ok` / `--missing` | `span` | Set / not-set, as a word with a tick or a warning colour |
| `.mm-interrupt`              | `ul`      | Things that are broken or blocking, **above** the band    |
| `.mm-interrupt__item`        | `li`      | One of them                                               |
| `.mm-interrupt__text`        | `span`    | The sentence. The `!` marker is drawn by CSS              |

Every `td` in a `.mm-quiet-table` needs `data-label="…"` matching its column heading:
below 760px the table becomes stacked rows and that attribute is the label.

**The interrupt.** Something broken may sit above the band, because it outranks the
routine. It is still a list of sentences with a link each — not a card, not a banner,
not a coloured box. The loud thing on a page is the band, and there is only one.

---

## Worked example: Processing Overview, before and after

**Before.** Three stacked `.mm-card .mm-dash-card .mm-module-surface` panels inside a
`.mm-bubble-stack`:

1. "Needs attention" (or "Get started") — a card containing a list of amber-filled rows.
2. "At a glance" — a card containing `.mm-proc-stats`, a `repeat(auto-fit, minmax(6.5rem, 1fr))`
   grid of five bordered `.mm-proc-stat` boxes: Processed, Failed, Success rate,
   Waiting, Running. All the same size, all the same weight, nothing leading.
3. "Libraries" — a card containing `.mm-proc-table` and a row of four secondary buttons.

**After.** A `.mm-quiet-stack` holding a `.mm-lead` and one `.mm-quiet-section`:

1. `.mm-interrupt` — the same attention sentences, borderless, above the band.
2. `.mm-lead-band` — six segments from the file census
   (`GET /api/v1/processing/files` → `status_counts`), in pipeline order: Waiting,
   On hold, Processing, Done, Skipped, Failed. Clicking one calls
   `onOpenTab("files", status)`, which the page turns into `?tab=files&status=…`; the
   Files tab already reads that parameter on mount, so the filter is real, not cosmetic.
3. `.mm-lead-caption` — what the band means, plus the two operator facts that used to
   be buried in the stats card (the settle time, and how many run at once), plus the
   one-sentence takeaway and the count of files in states the band does not draw.
4. `.mm-figure-row` — hero **Processed** (last 30 days) with *Rewritten* and *Already
   right* along its foot; supporters **Success rate** (with a meter) and **Reclaimed**.
5. `.mm-quiet-section` "Libraries" — the same table, now `.mm-quiet-table`, with the
   four buttons demoted to `.mm-quiet-link`s beside the heading.

The data the old page showed is all still there. "Waiting" and "Running" moved from
job counts to the file census, which is the same question asked of the better source.

Behaviour that did **not** change: the load-error branch, the loading branch, the
attention copy, the setup checklist, the rule-set summary strings, the media-type badge
suppression, the scan-interval wording.

---

## What NOT to do

1. **Do not touch the shell.** See above. This includes "just one padding tweak".
2. **Do not add a colour, a font, a shadow or a radius.** Only tokens already in
   `weir-tokens.css`. A new `--mm-*` token that is not pure layout is a rejection.
3. **Do not put a card anywhere below the lead.** No `.mm-card`, no `.mm-dash-card`,
   no `.mm-module-surface`, no `border` on a section. The figure tiles are the only
   bordered things outside the band, and they belong to rule 2.
4. **Do not build an equal-width tile row.** If you find yourself writing
   `repeat(auto-fit, minmax(…, 1fr))` for numbers, you are rebuilding the thing that
   was rejected.
5. **Do not invent a lead.** No band without a real "now"; no hero without a real
   number; no sparkline, trend arrow or percentage the API does not return.
6. **Do not draw a band of zeroes.** Route every empty through the table above.
7. **Do not make a segment or a row a clickable `div`.** Buttons and links only.
8. **Do not copy the mockup's class names.** `o1-*`, `o2-*`, `o3-*`, `o4-*`, `mk-*`
   are a throwaway static reproduction. The classes in this document are the real ones.
9. **Do not delete a test because it fails on the new markup.** Read it. If it is
   asserting layout, update the assertion. If it is asserting behaviour — a filter
   works, an empty state wins, a secret never reaches the DOM — keep it and make it
   pass.
10. **Do not leave superseded CSS behind.** When the last user of an `mm-proc-*`-style
    rule goes, delete the rule in the same PR.
11. **Do not widen a `data-testid`'s meaning.** Keep the ids the E2E suite uses
    (`tests/e2e/weir/test_app_navigation_audit.py` and friends) pointing at the same
    thing they pointed at before.
12. **Do not give a band segment a `min-width`, inline or otherwise.** The floor and the
    stacking threshold are one number and the primitive owns both; overriding one of them
    makes the band wrap again. See rule 1.
13. **Do not reach for a Tailwind utility to change something a `weir-*` class already
    sets.** It will be ignored without a word. See the section above.

---

## Gates

Run all of these in `apps/web` before opening a PR: `npm ci`, `npm run lint`,
`npm run format`, `npm test`, `npm run build` (which runs `check:tokens` and the
bundle budget). From the repo root: `node scripts/check-dead-code.mjs` and
`node scripts/check-agent-docs.mjs`.

Then look at the page. Dark and light, 1440 and 1024 wide, with data and on a fresh
empty install. Unit tests have let a blank page ship in this repo before.

If your page carries a band, look at it narrow as well — 390, and the width either side
of where it restacks — and check the claim rule 1 makes by measuring it, not by eye: at
every width, every segment's rendered width is at least that of every segment carrying a
smaller count, and the band is either one line or one line per segment. A band that is
neither is a wrapped band, and a wrapped band compares widths only within a row.
