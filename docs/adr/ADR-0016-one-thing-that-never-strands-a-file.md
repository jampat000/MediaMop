# ADR-0016: MediaMop is one thing, and it never strands a file

## Status

Accepted — supersedes the module premise in
[ADR-0007](ADR-0007-module-owned-worker-lanes.md), retires the last of the fixed scopes
left by [ADR-0014](ADR-0014-refiner-libraries-replace-fixed-scopes.md), and moves the
retention half of [ADR-0015](ADR-0015-media-manager-port-outbound.md) out of this
product entirely. [ADR-0013](ADR-0013-media-managers-are-kinds-not-products.md) survives
unchanged and is load-bearing here.

> **Update (2026-09-17):** Pruner was removed ahead of the `4.0` schedule below, by product
> decision in #473. Its retention job now lives in Deluno; migration
> ``0036_drop_pruner_tables`` drops its tables.

## Context

MediaMop has been built as a suite: a platform with modules, a dashboard that aggregates
across them, suite-wide settings, suite-wide pause, and worker lanes owned per module.
Two of the three modules have since been deleted or hollowed out — Subber went in `0010`,
Dashboard exists only to aggregate — and what is left is Refiner, which is the product,
and Pruner, which is not.

Three facts settle this, and the first one was wrong in our own heads for a long time.

1. **MediaMop is a stage in the middle of a pipeline. It never sees the library.** A
   manager picks a release and downloads it; the file lands in a completed folder;
   MediaMop takes it, works it, and writes it to an output folder; the manager imports
   and renames it onto storage. Every path MediaMop knows is `watched_folder` or
   `output_folder` on a library row. It has no view of what is on the NAS, has never had
   one, and should not acquire one. Any screen, metric or claim phrased as "your library"
   is a claim this product cannot support.

2. **Pruner needs library truth that only a manager owns.** Deciding what should stop
   existing requires knowing what is monitored, what is wanted, and what was already
   replaced. Pruner has none of that locally, so it asks over HTTP — which is the entire
   reason the outbound port and the "could not ask is not nothing" gate in ADR-0015 had
   to be built. In the manager's own process that is a local query. Pruner is also a
   generation behind architecturally: it never received ADR-0014, so its criteria are a
   column per filter on a singleton `pruner_scope_settings` row
   (`preview_include_genres_json` and friends), with a Python module per criterion and
   several rule families that only work against certain server kinds. Every new
   criterion is a new file and a new migration.

3. **The module layer costs more than it earns.** With one module, a module registry,
   cross-module aggregation, suite settings, suite pause and per-module lane boundaries
   are all ceremony around a single code path.

There is also a product failure hiding in the current design. When processing fails, the
file stays in `/work` with `processing_failed` and the manager never sees it. For a stage
in the middle of someone's pipeline, that is the worst available outcome: the user's
media is not on their NAS, and the tool that took it is the reason.

## Decision

1. **MediaMop is a single-purpose processing stage.** The `mediamop.modules.*` layer is
   removed. Refiner stops being a module and becomes the application. Suite settings,
   suite pause, module-owned lane boundaries and the aggregating Dashboard module go with
   it; one lane set serves the whole app.

2. **Custody is the subject.** The product's own account of itself — screens, metrics,
   docs, marketing — describes files it has taken responsibility for, between a manager's
   completed folder and that manager's import. Never "your library". The main screen
   answers: what arrived, what is in hand, what is stuck, what went back.

3. **Retention leaves, and becomes a complete action by doing so.** Pruner is deprecated
   in `3.0` with a pointer to its replacement and removed in `4.0`, **not before that
   replacement is live**. It moves to Deluno, where the library truth is local. This is a
   reimplementation, not a port: Deluno is .NET and carries no media-server client today,
   so the design transfers and the code does not.

   The move also fixes a defect in the current design rather than merely relocating it.
   Deleting from MediaMop is a dead end: the item is removed from a media server, and the
   manager — which still monitors it and still reads RSS — is free to download it again.
   In Deluno, one deletion can remove the file from disk, remove it from Plex, Jellyfin
   and Emby, unmonitor it, and blocklist the release so it is not re-acquired. Retention
   only actually works in the product that owns acquisition.

4. **A file is never stranded, and the manager is always told why.** Every library
   carries a failure policy with three settings:

   - `pass_through` (**default**) — the file is delivered to the output folder
     unmodified, on time, and recorded as passed through rather than failed. The
     guarantee is *worst case you get your original file, unchanged, on schedule.*
   - `hold` — today's behaviour, for users who would rather nothing reach their manager
     than something unprocessed.
   - `reject` — the file is deleted and the manager is told **why**, so it can act on
     that: blocklist the release, decline to re-grab it from RSS, and fetch a different
     one. A release carrying audio nothing can process is often best replaced rather than
     passed through, and only the manager can replace it.

   `reject` requires a reporting channel back to the manager that does not exist today.
   The outbound port from [ADR-0015](ADR-0015-media-manager-port-outbound.md) carries
   questions, not verdicts; this adds a reason-carrying failure report. Consistent with
   that ADR, a manager that cannot be reached is not consent: `reject` must fall back to
   `pass_through` rather than delete a file nobody can be told about. It is opt-in and
   never the default, because it destroys a file the user paid bandwidth for.

5. **Processing is what the operator configured, and nothing more.** MediaMop has no
   opinion about what a file ought to be — the manager already decided that at
   acquisition, against the user's quality configuration. If the configuration says strip
   subtitles, MediaMop strips subtitles and changes nothing else. There is no flow graph
   and no inference.

6. **Device compatibility is a read-only lens.** Files may be labelled with the devices
   they will and will not Direct Play on, and why. This is information attached to a
   file, never a target to conform toward and never an input to processing decisions.

7. **The product is renamed** as part of `3.0`, in the same release as the collapse,
   because both churn the same files and users should absorb one migration rather than
   two.

8. **Every decision explains itself in plain language.** A tool that rewrites other
   people's media must be able to account for what it did, why it did it, how, and what
   it chose not to do — in sentences an operator can read without knowing what a queue
   kind or an ffmpeg argv is. This is a product feature, not a debugging aid, and it is
   held to the existing [operator messaging standard](../operator-messaging-standard.md).
   The material is already captured: `refiner_files.status_reason` is described in the
   code as "a status and the sentence that explains it", and `refiner_file_log.detail_json`
   already stores admission decisions, probe results, the plan, the argv, cleanup gates,
   timings and sizes for every pass. None of it is currently narrated. The gap is
   presentation, not capture.

## Consequences

- One breaking major release. The rename lands as a mechanical commit with no behaviour
  change, and the de-modularisation lands on top of it, so both are reviewable.
- **Both environment variable prefixes are honoured for the whole `3.x` line**, with a
  startup warning on the old one. A Docker user who does not read release notes must not
  lose their install on upgrade.
- `media_scope` is retired along with the `/api/v1` surfaces that resolve `movie` and
  `tv` to a library.
- **The E2E visual smoke suite is rebaselined as part of this work, not after it.** Every
  screen changes, so every visual baseline is invalid; a suite left red through the
  migration cannot tell anyone whether a real regression landed. The suite is also
  already the flakiest gate in the repo — intermittent failures in a full run that pass
  in isolation, usually from a stale uvicorn or Vite process holding a previous
  `MEDIAMOP_HOME`. Rebaselining is the moment to fix that isolation properly rather than
  re-recording screenshots over a known-unreliable harness.
- The intake webhook stays generic per ADR-0013. Sonarr and Radarr users outnumber Deluno
  users and this product must keep working for them.
- The visual direction, including the custody framing of the main screen, is drafted at
  <https://claude.ai/artifact/JLUAA7uBm5taBAwNdh9mWv>.

## Deferred

- The name itself. `Mezzo` is the leading candidate — Italian for *middle*, and a nod to
  a mezzanine master, the intermediate file between source and delivery — pending
  availability checks on GitHub, Docker Hub and a domain.
- Whether any shared rule grammar is worth extracting across this product and Deluno's
  retention. The two operate on different corpora — a transient queue of files in custody
  versus a durable library at rest — so a shared engine is not assumed.
- Dry run over an entire watched folder (plan, no encode).
