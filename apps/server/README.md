# Weir server (.NET)

Weir's server: C# on .NET 10. It was ported from the Python backend area by area without changing the HTTP API, the web app or the SQLite schema, proven by the contract suite (`tests/contract`), and replaced it in #523, which deleted the Python backend. It is what the Docker image and the Windows package run. Why and how: [ADR-0017](../../docs/adr/ADR-0017-backend-on-dotnet.md).

Many comments and tests below still name the Python module or function a piece of code was ported from (`refiner_remux_rules.py`, `get_activity_recent`, ...). Those names are provenance: the Python code is in git history before #523, not in the tree.

| Project | Holds |
| --- | --- |
| `src/Weir.Host` | The process: configuration, logging, database startup, Kestrel, Windows Service and systemd support. Builds `Weir` / `Weir.exe`. |
| `src/Weir.Api` | Endpoints and HTTP behaviour (security headers, request ids, serving the web app). |
| `src/Weir.Infrastructure` | SQLite (connections, numbered migrations in `Migrations/`), filesystem, log files. |
| `src/Weir.Core` | Records and rules. No IO. |
| `tests/*` | xUnit tests for each project. |

## Build and test

Needs the .NET 10 SDK (pinned in `global.json`). From the repository root:

```powershell
dotnet build apps/server/Weir.slnx -warnaserror
dotnet test apps/server/Weir.slnx
```

## Run

It reads `WEIR_*` environment variables (documented in the repository's `.env.example`) and nothing else; it does not read a `.env` file itself (`scripts/dev-backend.ps1` loads one for it).

```powershell
$env:WEIR_HOME = "$env:TEMP\weir-dotnet"          # optional; defaults to %PROGRAMDATA%\Weir
$env:WEIR_WEB_DIST = "$PWD\apps\web\dist"          # optional; after `npm run build` in apps/web
dotnet run --project apps/server/src/Weir.Host -- --host 127.0.0.1 --port 8788
```

`--port` (what the Windows tray passes) wins over `PORT` (what the Docker entrypoint sets); both default to 8788 on every interface.

On startup the server creates an empty database at the current schema, opens a database already at the schema head `0036_drop_pruner_tables` without changing it, and refuses anything else with a message. It records its revision in the `alembic_version` table, the table the retired Python backend's Alembic migrations used, so every database a released Weir created still opens.

## Schema

**The .NET migrations in `src/Weir.Infrastructure/Migrations/` are the only source of the schema.** ADR-0017 froze the SQLite schema while both backends existed; that freeze ended with #523. The next schema change is a new numbered migration here (with its revision recorded in `alembic_version`, and `SchemaMigrator` taught to upgrade a database at the previous head), and it may diverge from the old Alembic head. There is no Alembic, and nothing regenerates a schema from Python.

`tests/Weir.Infrastructure.Tests/schema/alembic-head.sql` is the schema and seed rows the Python backend's last `alembic upgrade head` created, dumped before it was deleted. It is a frozen reference: `SchemaParityTests` builds a database from it and one from the .NET baseline migration and compares tables, columns, types, defaults, keys, indexes, foreign keys, SQL text and rows, which proves a database created by a released Python Weir is exactly what the baseline expects. When a later migration changes the schema, keep that comparison pointed at the baseline (it stays true) and test the new migration on its own; do not edit the reference file.

## Rules parity

`Weir.Core.Rules` is a port of Refiner's rules engine (`refiner_remux_rules.py`, `refiner_track_sorters.py`, `refiner_metadata_rules.py`, the pure parts of `refiner_original_language.py` and the display helpers). `tests/Weir.Core.Tests/Rules/golden/*.json` hold ffprobe-style inputs with the plan, notes and display lines the Python engine produced for them; `GoldenParityTests` requires the same answers.

**The golden files are .NET test fixtures now.** The Python generators (`scripts/generate-rules-golden.py`, `scripts/generate-ffmpeg-golden.py`) were deleted with the Python backend in #523, so nothing regenerates these files. A deliberate behaviour change updates the expected output by hand in the same change: an override file (below) for an existing case, or a new case file for new behaviour, with the issue number that justifies it.

### Golden overrides (deliberate divergence from Python)

Issue #537 fixed defects in the rules engine that the golden corpus had pinned as "today's behaviour" (its items 1, 2, 3, 5 and 6 — see the issue for each one). Rather than rewrite the recorded Python answers, a case whose correct answer now differs from Python's recorded one gets a same-named file in `tests/Weir.Core.Tests/Rules/golden/overrides/`, holding the issue number, which item(s) of it, and the new expected output, e.g.:

```json
{
  "issue": 537,
  "items": [1, 5],
  "expected": { "...": "the plan the fixed engine actually produces" }
}
```

`GoldenParityTests` reads this instead of the original file's `expected` for that one case; every other case is still compared against Python's recorded output, byte for byte. `sorters.json` holds several cases in one file, so its override has the same shape plus a `cases` list of `{"index": N, "expected": {...}}` keyed by position in that file's `cases` array, overriding only the cases named in it. `helpers.json` (issue #497 only) works the same way, except its override's per-case list is named `presets` (only that file's `presets` section — the dump of `TrackSorters.Preset(...)` — needs one). `Every_override_names_a_real_golden_case` guards against a stale or misnamed override file.

Issue #497 put a new `content_tier` key first in `TrackSorters.DefaultAudioSorters` (main over a dub/audio-description track over commentary), so every plan whose config used the default audio sorters (an empty `audio_sorters_json`) now writes a different "Track ranking: …" sentence as the first `audio_selection_notes` entry — 80 of the 106 `plan-*.json` golden cases needed a wording-only override for exactly that reason (an `issue_497` note alongside the pre-existing `issue: 537` entry where a case already had one), plus `sorters.json` and `helpers.json` for the sorter list and its presets. None of the 80 changed which track was kept — every one still names the same winner as before — and the other 26 plan cases and the rest of the corpus are untouched; `Issue497Tests` proves a dub or commentary track never wins the content tier over a main track regardless of quality.

### Known rules-engine gaps

- **Issue #537 item 4 (prefer the original language) is wired into the remux pass** (see "Remux pass" below): when a rule set keeps the original language, the pass asks the configured metadata provider (TMDb) about the film, runs `OriginalLanguage.SelectTracks` and plans with `WithOriginalLanguage`. It is proven by `RemuxPassRunnerTests.Issue_537_item_4_the_original_language_decides_the_kept_audio`. No contract scenario proves it end to end yet: `ExternalUrlPolicy` refuses a metadata provider on a loopback or private address, so the suite cannot point Weir at a fake TMDb, and no media manager port reports an original language.
- **Issue #495 (track flags from names)**, **#496 (regional language variants)**, **#497 (audio-keep-mode/subtitle-cap)** and **#498 (track naming/chapters)** are now wired end to end: persistence, the rule-set and preview APIs and the web rule set editor, on top of the engine work described below. See "Rule-set storage for #495/#497/#498" below for where the new fields live.
- **Issue #495 (track flags from names).** `Weir.Core.Rules.TrackFlagsReader.Detect` and `RefinerRulesConfig.RemoveHearingImpairedSubs` are wired into `RemuxRules.PlanRemux` (subtitle forced/hearing-impaired handling, audio commentary/dub/audio-description). The rule set editor's Subtitles section has a "Remove hearing-impaired subtitles" checkbox, off by default.
- **Issue #497 (keep one audio track per language; cap subtitles per language).** `RefinerRulesConfig.AudioKeepMode` (`single`, the default and today's behaviour, or `per_language`), `SubtitleMaxPerLanguage` (0 = unlimited, the default) and `SubtitleQualityStrategy` (`text_first`, the default, `image_first` or `accessibility`) are wired into `RemuxRules.PlanRemux`: `per_language` keeps the best track (by the configured sorters, variant-aware via `LanguageVariants.Matches`) of each configured language slot that has one, in slot order, with `DefaultAudioSlot` (primary by default) marking the default track, and never keeps zero audio; the subtitle cap groups matched candidates by the language slot they matched, exempts a track kept under `PreserveForcedSubs`, and otherwise keeps the best `SubtitleMaxPerLanguage` per group by format (text over image, or the reverse under `image_first`) then type (regular over SDH over forced, or SDH first under `accessibility`), noting every drop with a reason. The editor's Audio section has an "Audio tracks kept" choice and the Subtitles section has the per-language cap and strategy, shown only while the cap is non-zero. See `Issue497Tests` for the engine behaviour and `GoldenParityTests` for proof that `single` mode and an unlimited cap (both defaults) still behave exactly as before.
- **Issue #496 (regional language variants).** `Weir.Core.Rules.LanguageVariants.DetectVariant(title, baseCode, bcp47Tag)` tells apart Quebec/France/Belgium French, Castilian/Latin American Spanish, Brazilian/European Portuguese, Traditional/Simplified Chinese, Cantonese, Mandarin and Flemish from a track's name or an explicit BCP 47 region/script subtag. An identifier is `{base}-{REGION}` (`fre-CA`, `por-BR`), `{base}-{region}` with a UN M49 region (`spa-419`), `{base}-{Script}` (`zho-Hant`, `zho-Hans`), or a bare ISO 639-3 code offered as a refinement of a macrolanguage (`yue`, `cmn`); `base` is a fixed canonical spelling per entry, not necessarily the input tag's own spelling. Detection is refine-only: an explicit region/script subtag is read directly and never overridden by the name; a self-identifying marker (`VFQ`) works on an undetermined track or one whose base language already agrees, but never on a conflicting one; a refine-only marker (bare `Latino`, `Europeu`, `Traditional`) only ever applies once the base language already agrees. `RemuxRules.PlanRemux` computes it for every audio and subtitle candidate and matches it against `PrimaryAudioLang`/`SecondaryAudioLang`/`TertiaryAudioLang` and `SubtitleLangs` (via `LanguageVariants.Matches` and `NormalizeLanguageOrVariant`): a plain base value (`"fre"`) still matches every variant, unchanged; a variant value (`"fre-CA"`) matches only that exact variant. A detected variant on the selected audio track adds a plan note (`"French (Canada), from the track name 'VFQ'."`). No new storage or API is needed for this one: the audio preference slots and `subtitle_langs_csv` are already plain strings, so a variant identifier round-trips through the existing fields unchanged. `apps/web/src/lib/refiner/language-variant-options.ts` mirrors the C# table by hand (identifier, display name, base language) so the web audio-slot and subtitle-language pickers can list each variant under its base language (an `<optgroup>` for the single-choice audio slots; an indented entry in the flat multi-select picker for subtitle languages) without a round trip to the server. See `LanguageVariantsTests` for the detection table and the wiring, and `GoldenParityTests` (585 pre-existing cases, unchanged) for proof that a plain-language rule still behaves exactly as before.
- **Issue #498 (standard track names, clear video names, remove chapters).** See "ffmpeg parity" below for the engine (`Weir.Core.Rules.TrackNaming`, `MetadataRules`, `FfmpegCommands`). The editor's "Track naming & chapters" section has the standardize-names toggle, a template field with a live client-side preview and inline unknown-placeholder error (`apps/web/src/lib/refiner/track-name-preview.ts`, a hand-written mirror of `TrackNaming.Render`/`ValidateTemplate` — illustrative only; the server's `TrackNaming.ValidateAll` is still the source of truth on save), the four per-flag overrides (each with its own preview), clear-video-names and remove-chapters toggles.

### Rule-set storage for #495/#497/#498

ADR-0017 freezes the `refiner_rule_sets` schema until the backend switch-over (#523), and none of these
fields exist in the Python schema, so **no migration was added**. Instead, all of them are packed into the
existing `subtitle_sorters_json` TEXT column, chosen because — unlike `audio_sorters_json` — it is written
and read back by the API and the web "Subtitle order" editor but never consumed by the planner itself, so
extending its format cannot change any plan a saved rule set produces. `Weir.Core.Refiner.RuleSetRuleExtras`
documents and implements the exact encoded shape (`{"sorters": [...], "rule_extras_v1": {...}}`); a legacy
value — empty text, or the bare sorter array this column has always held — decodes with every new field at
its shipped default, so an upgrade changes nothing, and a value missing individual `rule_extras_v1` fields
(written by an older or a newer server) defaults those fields the same way. `Weir.Infrastructure.Refiner.LibraryStore`
is the only place that packs/unpacks the column; everywhere else — `RefinerRuleSetRecord`, `LibraryRules.RuleSetInput`,
`RuleSetConversion.ToRulesConfig`, `RemuxPassPaths.RulesConfigFor`, and the rule-set and preview API bodies —
sees plain, discrete fields (`remove_hearing_impaired_subs`, `audio_keep_mode`, `subtitle_max_per_language`,
`subtitle_quality_strategy`, `standardize_track_names`, `track_name_template`, `track_name_overrides`,
`clear_video_track_names`, `remove_chapters`), so the storage trick is invisible outside that one file. Both
`RuleSetConversion.ToRulesConfig` (the rule-less/seeded-library fallback) and `RemuxPassPaths.RulesConfigFor`
(the path a real pass and the #502 preview take) map every new field the same way. Validation matches the
engine's: `AudioKeepMode`/`SubtitleQualityStrategy` are closed enumerations and `SubtitleMaxPerLanguage`'s
"no negative" rule are enforced at the HTTP boundary (`BodyModel.Literal`/`Number(ge: 0)`, a 422), the same as
every other rule-set enum/numeric field; `track_name_template` and `track_name_overrides` are validated with
`TrackNaming.ValidateAll` — an unknown placeholder is a 400, the same pattern `TrackSorters.Validate` already
uses for the sorter JSON columns.

## ffmpeg parity

`Weir.Core.Media` ports the decisions in `refiner_remux_mux.py` and `refiner_hardware_acceleration.py`: ffprobe and ffmpeg command lines (token for token), unreadable-media classification, output and duration validation, progress parsing and hardware choice. `Weir.Infrastructure.Media.MediaTools` runs the tools through `IProcessRunner` (`ProcessRunner` kills the whole process tree on timeout or cancellation). `tests/Weir.Core.Tests/Media/golden/*.json` record what the Python functions did with their processes replaced by recorded inputs, including log payloads and exception messages; `MediaGoldenParityTests` and `MediaToolsGoldenTests` require the same. Like the rules corpus, these are maintained as .NET fixtures now (see "Rules parity").

`RealFfmpegTests` run real ffprobe and ffmpeg on files generated with `-f lavfi`. They skip unless the tools are found through `WEIR_FFMPEG_DIR` or `PATH`; on Windows, point `WEIR_FFMPEG_DIR` at a packaged build's `server/bin/ffmpeg` or at `packaging/windows/vendor/ffmpeg` after a package build.

### Deliberate divergences from the golden fixtures

Golden parity pins today's Python behaviour, bugs included. Fixing one of those bugs (#539) makes the .NET port behave differently from the Python code the golden fixtures were captured from on purpose, so regenerating the fixtures from Python would erase the fix instead of proving it. Where a case's expected value changed for this reason, the fixture stays as Python produced it and the test that reads it patches the loaded expectation instead — a small `GoldenDivergences` helper next to each affected test class (`Weir.Core.Tests.Media.MediaGoldenParityTests` and `Weir.Infrastructure.Tests.Media.MediaToolsGoldenTests`), named for the GitHub issue that required it. Every case the fix does not touch still runs against the unmodified fixture, so the suite keeps proving parity everywhere it still holds. #539 item 1 is the current entry: ffprobe now runs with `-v error` instead of the fixture's `-v quiet`, which changes the recorded argv and the `REFERENCE_FFPROBE_CALL` log line (and, for a probe timeout, the `Command '[...]' timed out` message) but nothing else in either fixture.

Fixed in #539, real ffmpeg tested (`RealFfmpegTests`) and documented here:

1. **Unreadable media on real files.** ffprobe ran with `-v quiet`, so its diagnostics never reached stderr and `MediaUnreadableException` could never fire outside of scripted tests. It now runs with `-v error` (`FfmpegCommands.BuildFfprobeArgv`); verbosity does not affect `-print_format json`, so stdout is unchanged. A zero-filled `.mkv` (the exact repro in #494) is now classified unreadable.
2. **Hardware acceleration reaching the executed command.** `MediaTools.RemuxToTempFileAsync` built its own argv for `RunFfmpegAsync` without the caller's decided acceleration flags, so a library configured for hardware decoding always ran in software. `RemuxToTempFileAsync(..., acceleration:)` now threads an `AccelerationDecision` into the same `FfmpegCommands.BuildRemuxArgv` call used for both the debug-log summary and the executed argv, so the two can no longer diverge.
3. **Truncated Matroska passing validation.** A Matroska file cut in half keeps its full header duration, so `ValidateRemuxOutputAsync`'s duration check passes it; `ValidateMediaIntegrityAsync`'s full demux also exited 0 on this ffmpeg build, only warning `File ended prematurely`. It now fails when that exit-0 read carries a marker in `ProbeOutput.IntegrityIncompleteMarkers` (`"file ended prematurely"`, `"truncating packet"`, `"partial file"`), and — where practical, i.e. whenever ffmpeg reported at least one timestamp — when the last decoded timestamp (`-progress pipe:1`, reused on this read) falls short of the probed duration by more than the same tolerance `ValidateRemuxOutput` uses.
4. **A silent progress run never timing out.** The reference's progress loop only checks its timeout as a line arrives, so a process stuck reading its input (and so never writing a line) hangs forever. `ProcessRunner`'s timeout is a wall-clock timer, independent of stdout activity, so this was already fixed by the port; `ProcessRunnerTests.A_progress_run_that_never_writes_a_line_is_still_stopped_by_the_timer` and `RealFfmpegTests.A_progress_run_that_never_writes_a_line_is_still_stopped_by_the_timer` (a real ffmpeg blocked on an unconnected named pipe) keep it proven.
5. **Smaller decisions, recorded and tested:**
   - The `"end of file"` unreadable-media marker is narrowed: ffmpeg's own `av_strerror` text for a plain `AVERROR_EOF` is the bare phrase "End of file", which still means the content is bad, but the same underlying error qualified as `"premature end of file"` or `"unexpected end of file"` is ffmpeg's wording for a truncated or still-downloading file — a completeness problem, not evidence the content itself is unreadable — so those two phrasings are excluded (`ProbeOutput.FailureFor`).
   - A plain (non-progress) ffmpeg timeout raises `MediaToolTimeoutException`, the same classified error probing uses, instead of leaking `subprocess.TimeoutExpired` uncaught as the reference does.
   - A timeout, in either ffmpeg mode, kills the whole process tree, not just the direct child — some hwaccel and filter setups spawn helpers that would otherwise survive and keep the output file open.
   - Hardware detection decodes `ffmpeg -hwaccels`' output as UTF-8 with replacement (`ProbeOutput.CapturedText`), like every other tool output this layer reads, instead of the reference's locale encoding.
   - The integrity check runs on every platform. The reference skips it on Windows (`if os.name != "nt"` in `file_remux_pass/run.py`), reasoning that Windows write handles are exclusive so a reader can never see a half-written file; that does not hold for every way Weir sees a file arrive on Windows (SMB shares, WSL2 bind mounts, downloaders that preallocate then write), and #494 was itself filed against a Windows rig. `MediaTools.ValidateMediaIntegrityAsync` makes no platform distinction; a future caller should not reintroduce one without a concrete, current reason to.

6. **Chapters on every probe (#498).** The reference never asks ffprobe for chapters. `FfmpegCommands.BuildFfprobeArgv` now adds `-show_chapters`, so every probe's JSON carries a `chapters` array (`ProbeResult.Chapters`, empty when the file has none) for `RemuxRules.IsRemuxRequired`'s "remove chapters" check, without a second probe call. This only adds a `chapters` key to the parsed result; the argv fixtures and the two places that log the ffprobe argv literally (`REFERENCE_FFPROBE_CALL` and a probe timeout's message) are patched at the one new token, same mechanism as item 1.

#498 also adds `MetadataRules.StandardizeTrackNames` / `TrackNameTemplate` / `TrackNameOverrides`, `ClearVideoTrackNames` and `RemoveChapters` — new options with no Python equivalent yet (all off by default, so every existing golden case and argv is unchanged), rather than a divergence from one. `Weir.Core.Rules.TrackNaming` is the template engine (`{language}`, `{variant}`, `{channels}`, `{codec}`, `{flags}`); `FfmpegCommands.BuildRemuxArgv` writes `-metadata:s:a:N`/`-metadata:s:s:N` titles and `-metadata:s:v:N title=` (clearing) at each track's output index, and `MetadataStreams.ArgvFlags` adds `-map_chapters -1`. Tested in `Weir.Core.Tests.Rules.TrackNamingTests`, the "track names and chapters" section of `MetadataRulesTests`, and (real ffmpeg) `RealFfmpegTests.A_remux_standardizes_names_clears_video_titles_and_removes_chapters`.

Fixed in #547 (found by the #503 trial, `docs/trials/503-mkvmerge-vs-ffmpeg.md`), real ffmpeg tested (`RealFfmpegTests`) and documented here; every remux argv case with a kept audio or subtitle track changed (`GoldenDivergences.RemuxArgv` in `MediaGoldenParityTests`), since items 2 and 3 touch every one of them:

7. **Attachments silently dropped on every remux.** `FfmpegCommands.BuildRemuxArgv` never mapped `codec_type=attachment` streams, so a font attached for an ASS/SSA subtitle was lost even with `MetadataRules.RemoveAttachments` off. It now adds `-map 0:t?` (ffmpeg's attachment stream-type specifier; the `?` makes a source with none a no-op) unless `RemoveAttachments` is on, or the output is one of the `.mp4`/`.m4v`/`.mov` extensions sharing the mov,mp4,m4a,3gp,3g2,mj2 muxer, which refuses an attachment output stream outright ("Attachments are not supported in QuickTime/MP4", confirmed against the bundled ffmpeg) — Weir's remux always keeps the source's own extension, so this only ever matters for a source that was already one of those formats. An attachment's own `filename`/`mimetype` tags are copied through the same way any directly-mapped stream's metadata is, with one exception: when `MetadataRules.RemoveOtherMetadata` also emits `-map_metadata -1`, that erases an attachment's tags too — unlike every other stream type, Matroska requires an attachment to carry a `filename` tag at all, so without a fix ffmpeg would refuse to write the file ("Attachment stream N has no filename tag", also confirmed against the bundled ffmpeg). `-map_metadata:s:t 0:s:t` is added right after `MetadataStreams.ArgvFlags` in that case, restoring only the attachment stream type's own metadata.
8. **Disposition flags overwritten instead of edited.** Kept audio and subtitle tracks got `-disposition:a:N default|0` / `-disposition:s:N default+forced|default|forced|0`, which set the disposition to *exactly* that value — clearing `comment`, `dub`, `original`, `descriptions`, `hearing_impaired` and any other flag the source track had, since none of those were ever restated. It now uses ffmpeg's additive syntax, `+default`/`-default` (audio and subtitles) and `+forced`/`-forced` (subtitles), verified against the bundled ffmpeg's `-dispositions` list and real remuxes: unlike a flat value, `+flag`/`-flag` only ever changes the named flag on top of whatever ffmpeg already copied through from the source stream's own disposition, so a kept commentary track keeps its `comment` flag through a remux that changes `default`.
9. **Stale per-track statistics tags carried forward.** A plain `-c copy` remux never touches the elementary stream, so mkvmerge's own per-track statistics tags (`DURATION`, `NUMBER_OF_FRAMES`, `NUMBER_OF_BYTES`, `BPS`, `_STATISTICS_WRITING_APP`, `_STATISTICS_WRITING_DATE_UTC`, `_STATISTICS_TAGS`) and ffmpeg's `ENCODER` tag survive unchanged from however that stream was originally produced, even when the remux changes the track set around it — stale lineage a player may show as if it described this file. `FfmpegCommands.BuildRemuxArgv` now clears all eight keys (`-metadata:s:{v,a,s}:N KEY=`) on every kept video/audio/subtitle output stream, indexed by output position like the dispositions. Matroska's own muxer recomputes a track's `DURATION` tag from the packets it actually writes regardless of this clear (confirmed against the bundled ffmpeg, including after a track is dropped), so nothing is lost by clearing it up front, and a stream with no such tag to begin with is unaffected.

## Jobs and workers

The durable queue is the `refiner_jobs` table the Python backend used, used the same way: the same statuses, dedupe keys, claim statement, lease checks, retry backoff and failure wording, and the same timestamp text, so a row a released Python Weir left behind is claimed, finished or recovered correctly. (Cross-backend tests that ran the Python queue against the same database proved this until #523 deleted the Python backend.)

- `Weir.Core/Jobs`: the rules (job kind guard, admission, schedule grid, backoff, failure wording, recovery wording, Weir's temp file names).
- `Weir.Infrastructure/Jobs`: `RefinerJobStore` (SQLite), `RefinerJobProcessor` (one worker pass), startup recovery, history retention, periodic enqueue and the hosted services. `AddWeirJobs` registers all of it.
- Shared by every area: `Weir.Core/Activity` (the event types, `ActivityClassifier` and `IActivityWriter`, with the one insert in `Weir.Infrastructure/Activity/SqliteActivityWriter`), `Weir.Core/Observability` (operator failure wording), `Weir.Core/Json/PyStrings` (Python `str` slicing, `strip()` and `repr()`), `Weir.Core/Time` (`PyDateTime`, IANA `TimeZones`) and `AddWeirPlatform` (the shared singletons).
- Periodic work (`IPeriodicTask`: session cleanup, log retention, configuration backup, history retention) runs in `PeriodicTaskService` with the Python loops' timing: run at start or after one interval, then every interval, with a shorter cooldown after a failure where Python has one. It starts after startup recovery.
- Job handlers implement `IJobHandler` and are registered as singletons by the area that ports them.

**Unported job kinds are not claimed.** Python's worker claims every eligible row and fails any kind it has no handler for. While handlers are still being ported, a .NET worker doing that would fail real work, so it claims only kinds with a registered handler, plus retired or unprefixed kinds, which it claims only to refuse with Python's wording. Everything else stays `pending` for a backend that can run it. Periodic families are timed only when their kind has a handler, for the same reason.

Startup recovery also fixes #534: besides requeuing leased rows and removing `.partial` outputs, it removes the remux temp output of interrupted jobs, and any other remux temp output at the top of a library work folder. Only Weir's exact temp names (`{stem}.refiner.XXXXXXXX{suffix}` and the dry-run placeholder) are ever deleted.

## Remux pass

`Weir.Infrastructure/Refiner/RemuxPass` ports `file_remux_pass/` (`run.py`, `handlers.py`, `visibility.py`, `paths.py`) and what the pass calls: file settling and the source read guard, output collisions, sidecar migration, the guarded copy/link/finalize writes, the Movies release-folder cleanup, the Movies and TV output-folder cleanups with the manager library-truth gate, `record_failure` and the retry policy, the processing record and the live progress row. The pure parts are in `Weir.Core/Refiner/RemuxPass`. `AddWeirRemuxPass` registers `RemuxPassHandler`, so .NET workers now claim `refiner.file.remux_pass.v1`, and replaces the jobs port's `NoUnhandledJobFailureRecorder` with `RemuxPassFailureRecorder`, so a handler crash is recorded against the file with the failure policy applied.

Behaviour matches Python except these deliberate changes:

- **#539 items 2, 3 and 5.** The acceleration flags decided for a pass reach the executed ffmpeg, the integrity read runs on every platform (not only off Windows) and is given the probed duration, so a truncated Matroska file waits instead of being published.
- **#500.** The staged-output check the pass runs before publishing (a freshly remuxed temp file, an unchanged hard-linked or copied file, and the detached copy after a hard link's source survives) is `MediaTools.ValidateStagedOutputAsync`, not the reference's `validate_remux_output`. It checks the whole plan — container family, track type/count/disposition/language at every output position, a duration expected from the max of the *kept* source streams (not the whole source, so a dropped long subtitle track no longer looks like truncation) with a tightened `max(0.5s, 1%)` tolerance, new ffprobe `-v warning` diagnostics the source did not have, and a cleared container title — instead of just an audio count and a duration floor (`Weir.Core.Media.RemuxOutputValidation`, ported from Muxarr's `OutputValidator`). A mismatch is `MediaToolException`/`MediaCompletenessException`, the same execution-failure classification as any other remux failure, so it is never mistaken for evidence the release itself is bad. `ProbeOutput.ValidateRemuxOutput` (the older `expected_audio`-count check) is kept only so `MediaGoldenParityTests`/`MediaToolsGoldenTests` can still prove parity with the Python reference's original check; nothing in this pass calls it any more.
- **#537 item 4.** The original-language option now decides the preferred audio (see "Known rules-engine gaps").
- **#531 item 2.** A retry or requeue whose payload has lost its hand-off origin gets it back: `HandoffOriginCarry` finds the origin on the most recent job for the same file, and only while that hand-off has not already been answered (completed, passed through, rejected or cancelled in the ledger). `RemuxPassHandler` uses it when a payload has no origin, and `RequeueStore` copies it into a manual requeue, so the final completion, hold or hand-back is reported with its output path. The watched-folder scan port should call it too when it builds a retry payload. Item 1 (the fingerprint recorded at intake) and item 3 (`scheduled` while a retry is owed) were already fixed by the media managers port.
- **#534** is already handled by startup recovery; `test_crash_temp_output.py` now proves it end to end against a pass killed mid-remux.
- The source fingerprint's device and inode come from `GetFileInformationByHandle` on Windows; elsewhere .NET has no portable inode, so they are 0 and a replaced file is caught by size and modification time.

### Seams for work ported separately

- **`ITvSeasonFolderCleanup`** (`refiner_tv_season_folder_cleanup.py`). It needs the manager queue-row mapping the watched-folder scan port brings (the row-to-view mapper itself, `queue_adapter.py`, is ported as `Weir.Core.Refiner.QueueRowAdapter` for the failure-cleanup sweep below, but nothing yet wires it into this seam's title/year anchor fallback). The default, `SkippedTvSeasonFolderCleanup`, records the season-cleanup fields as a skip with a plain reason and removes nothing, so a successful TV pass leaves its season folder in the watched folder until then.
- **`IOriginalLanguageLookup`**: `MetadataProviderOriginalLanguageLookup` asks the configured provider about films; TV episodes and unreadable names decline, leaving the language preferences in charge.

## Pass-through, reject and failure cleanup (#522 part 4)

`IFailurePolicy`'s two follow-up kinds now have handlers, registered by `AddWeirRefinerFailureFollowUps` (called instead of `AddWeirRemuxPass` directly; it calls that in turn):

- **`RefinerPassThroughHandler`** claims `refiner.file.pass_through.v1` (port of `refiner_pass_through.py`'s handler): copies the original into the output folder unmodified (`PassThroughDelivery`, verified byte-identical to the source, never as valid media), records the delivery, and reports a waiting manager's hand-off complete once something was actually delivered. A copy failure is recorded in Activity and re-raised as `AlreadyRecordedFailureException` so the generic worker-failure path (`RemuxPassFailureRecorder`, unchanged, already handles every job kind) does not record it twice.
- **`RefinerRejectHandler`** claims `refiner.file.reject.v1` (port of `refiner_reject.py`): a hand-off route (capability-gated on `processor-reject-regrab`, reported first, removed second) and an arr-queue route (exact-one-match plus a single-video-file safety check before `IMediaManagerPort.RemoveQueueItemAsync`), paced process-wide (`RejectPacing`, an async wait rather than Python's blocking `time.sleep`). Anything short of certainty falls back to a pass-through, unconditionally (not gated by the library's failure policy again).
- **`RejectSupportEvaluator`** (port of `reject_support`) backs `GET /api/v1/refiner/reject-support` and the same check on saving a library (`RefuseUnsupportedRejectAsync` in `RefinerLibraryEndpoints`), both previously stubbed.
- **`RefinerFailureCleanupSweep`** (port of `refiner_failure_cleanup.py`) runs the two job kinds `JobServices.cs` already scheduled (`FailureCleanupSweepEnqueuer`, from the jobs port) but that had no handler yet: it deletes a failed release's source (and, for Movies, output) folder and its work-temp leftovers once every covering manager confirms nothing still imports it. Its "still held by a manager" check uses `QueueRowAdapter`'s exact output-path match only (Python's `_held_by_manager`); it does not fall back to the title/year anchor `CandidateGate` uses elsewhere, since the row attribution needed for that (`manager_queue_signals.py`) is scan-port work.

Fixes included:

- **#532.** A rejection always upserts a Files row (`RemuxPassFileState.UpsertRejectedAsync`) with status `rejected`, the reason and the failure class, whether or not a watched-folder scan had already recorded the file — Python's `mark_file_status` is a no-op with no existing row, which is exactly the bug.
- **#531 item 2 (remainder).** The origin-carry fix already covers pass-through and reject: since both are enqueued with whatever origin the caller resolved (carried by `HandoffOriginCarry` beforehand, or attached directly), their own completion/rejection report always has an output path or a disposition to send. `RequeueStore.RequeueFileAsync` (a human's "retry now") carried it too, but `RefinerWatchedFolderScanDispatchJobHandler.EnqueueRemuxPassAsync` — the automatic, scan-driven retry, and the only path that requeues a `processing_failed` file without an operator clicking anything — did not: a hand-off retried by a scan cycle (the common case; a real remux failure is retried on the next watched-folder scan, not by hand) lost its origin and its eventual pass-through/reject was reported to nobody. Fixed the same way: it now calls `HandoffOriginCarry.FindAsync` too before building the job payload. `tests/contract/processing/test_handoff_retry_correctness.py::test_pass_through_after_a_retry_reports_a_completion_callback_with_output_path` (previously `known_bug(issue=531)`) proves it.
- **#539 / #494 end to end.** A zero-filled `.mkv` under the `reject` policy now genuinely rejects: unreadable-media classification (#539 item 1, already fixed in the ffmpeg layer) triggers `reject_bad_release` inside `RemuxPassHandler`, which queues `refiner.file.reject.v1`; the handler above then reports the Deluno hand-off `failed` with `disposition: rejected` — proven by `RefinerRejectHandlerTests` and the reject-through-handoff path, never `completed` with a copy.

## Library mode: safe swap (#506)

`Weir.Infrastructure/LibraryMode` replaces a library file with its cleaned copy so that a crash, power cut, locked file or concurrent change can never lose it or overwrite a newer one. It is .NET only (no Python counterpart). The library-mode job flow (#505, below) calls `SafeSwap.RunAsync` with a writer (ffmpeg) and an `ISwapOutputValidator`, and `SwapRecoverySweep` now runs at startup (`JobsStartupRecoveryService`, right after the existing job/temp-file recovery, before any worker claims a job) over the union of every library's configured folders. The pure rules (names, space margin, in-use backoff, wording) are in `Weir.Core/LibraryMode/SafeSwapRules`.

- **Preflight:** the file exists; its link count is 1 (else skipped as seeding, unless the library allows hardlinked files); the volume has the file's size plus 1 GiB free; a probe file can be written beside it; it is not read-only; no other program holds it; its fingerprint (`SourceFiles.Fingerprint`, as the remux pass) is recorded.
- **Write and check:** `<name>.weir-tmp<ext>` beside the original, then the validator.
- **Commit:** re-fingerprint (changed → discard, "The file changed while Weir was working; nothing was replaced"); copy permissions (Windows DACL; POSIX mode bits, and owner when root; never the mtime); rename original → `<name>.weir-bak<ext>` and check the backup is still the fingerprinted file; rename temp → original name (the commit); record it; delete the backup (a failure is logged and left for the sweep).
- **Renames** are same-folder and never replace an existing file: `MoveFileExW` with only `MOVEFILE_WRITE_THROUGH` on Windows (no replace, no copy fallback), `File.Move(overwrite: false)` elsewhere.
- **Rollback and sweep** judge from the files alone: backup present and original missing → rename it back; backup and original present → delete the backup; temp → delete. A locked file (sharing violation, `EBUSY`) is the `InUse` outcome, requeued after 5, 15 and 60 minutes (`SafeSwapRules.InUseRetryDelay`).
- **Persistence:** progress is recorded on the job row, not in a new table, because ADR-0017 kept the SQLite schema fixed until the switch (#523). `RefinerJobSwapJournal` adds `library_swap` (`state`: `writing`, `committing`, `committed`, `finished`, `rolled_back`, `recovered`, plus the three paths) and `swap_committed: true` to `refiner_jobs.payload_json`, keeping every other key. The sweep visits the paths of unfinished swaps first; walking library folders is a fallback. No migration and no schema-parity change.
- **Tests:** `SafeSwapTests` injects a failure, a failure after the effect, a crash and a crash after the effect at every one of the swap's 23 filesystem and journal operations and proves exactly one intact file remains (original content before the commit rename, cleaned content after), with the journal alone enough to recover every crash. `PhysicalSwapTests` run the swap and sweep on real files and a real job row, including a file held open by another handle.

### Fixed in #545

Defects the .NET port kept parity with while porting the remux pass (#522 part 3), fixed afterwards in .NET only.

1. **Output-folder cleanup could delete a folder before a manager imported it.** `LibraryTruthGate.EvaluateForFolder` used to clear a folder for deletion whenever every reporting manager had no *conflicting* file sitting inside it — which is exactly what a manager that has not scanned or finished importing yet (or one that imports by copy and scans later) looks like. It now also requires positive evidence the release was picked up: a manager's own reported library names this exact output path anywhere (not only inside the folder), or the same title (file-name stem) at a different path, which is how a manager that renames or reorganises on import records it — or the hand-off ledger already recorded this pass's outcome as `completed`/`passed-through` (`IPostSuccessCleanupData.HandoffOutcomeAcknowledgedAsync`). Absent either, the folder is left in place regardless of age. The existing movie/TV output-cleanup minimum-age settings (`WEIR_REFINER_MOVIE_OUTPUT_CLEANUP_MIN_AGE_SECONDS` / `..._TV_...`, floored at one hour) double as the manager's import window: nothing is ever removed before that age, confirmed or not. `tests/contract/processing/test_output_folder_cleanup.py` proves it end to end with a fake Radarr that reports an empty library and a companion test proving the folder is removed once the manager confirms the import.
2. **Pass-through and reject jobs deduped forever.** Their dedupe key was `{kind}:{library}:{path}` alone, so once one finished, a later failure of a replaced file (e.g. a re-download with the same name) never queued another. `QueueingFailurePolicy.FingerprintTag` (built on `SourceFiles.DedupeFingerprintTag`: size and modification time) is now folded into the key, so a changed file gets a fresh key while a repeat enqueue for the same, unchanged file still dedupes against the row already there. `HandoffLedgerStore.JobsForAsync` matches the base key as an exact match or a prefix, so the ledger keeps finding these jobs regardless of the fingerprint suffix.
3. **An undelivered pass-through or reject reported nothing.** Once such a job exhausted its own retries it dropped out of `JobsForAsync`'s pending/leased filter and vanished from the hand-off status API. `JobsForAsync` now also returns a `failed`-status row for these two job kinds, and `HandoffLedgerStore.CurrentStatusAsync` reports a pending one as `scheduled` (never `queued` — that field means the remux queue, not a decided disposition about to run) or `working` while leased, and a permanently failed one as `failed` with the job's own `last_error` as the reason.
4. **Stored subtitle mode wasn't normalized on both rule-config paths.** `RemuxPassPaths.RulesConfigFor` (the live pass) used to pass the stored mode through unchanged, while `RuleSetConversion.ToRulesConfig` (the rule-less fallback) normalized it. Both now call `RuleSetConversion.NormalizeSubtitleMode`.
5. **Measured media facts and collision decisions landed on every library's row.** `RemuxPassFileState.RecordMeasuredMediaFactsAsync` and `RecordOutputCollisionAsync` matched on `relative_path` alone, so two libraries that happened to share a path both got the write. Both now also filter on `library_id` (threaded through as `MeasuredMediaFacts.LibraryId` and a new `libraryId` parameter, from `RemuxPassRequest.LibraryId`/`PassThroughDeliverySettings.LibraryId`); a null library id skips the write rather than falling back to the old cross-library match.

### Manual track plans (choosing tracks by hand, issue #501)

`GET /api/v1/refiner/files/{id}/tracks` and `POST /api/v1/refiner/files/{id}/manual-plan` let an
operator finish a held file by hand instead of changing a library's rules. It was built in
C# only, while ADR-0017 still froze the SQLite schema, so it adds no migration.

- **No migration, no new column.** The chosen plan is never persisted as file state; it lives only
  in the enqueued job's `payload_json`, alongside the source fingerprint taken at submission time
  (`manual_plan` and `source_fingerprint`, see `ManualPlanJson`). This is why: the schema was frozen
  when it was built (it no longer is, since #523, but nothing here needs a table), a manual plan is a one-off instruction for exactly one queued pass rather than a durable setting,
  and the job row already is the mechanism Weir uses to carry a one-time instruction to a worker
  (compare `pass_through_unchanged` and `origin` on the same payload). If the pass fails, the
  operator chooses again from a fresh probe rather than a stale plan being retried blind.
- **`GET .../tracks`** (`Weir.Api/Endpoints/RefinerFilesEndpoints.cs`, `ManualPlanSupport.LoadAsync`)
  re-probes the held source with ffprobe — never the last recorded metadata — and returns every
  stream (video, audio, subtitle, image, attachment) with its codec, language, title, channels and
  disposition, plus what the saved rules would do with it and why. The reasoning comes from
  `Weir.Core.Rules.RemuxRules.ExplainTracks`, a read-only, per-stream account of the same decisions
  `PlanRemux` makes (candidate ranking, commentary/hearing-impaired exclusion, language matching),
  so the UI can show a reason next to each row without duplicating the engine's logic by hand.
- **`POST .../manual-plan`** (operator + CSRF) takes `{keep: [{index, default, forced}], order}`,
  re-probes to validate every index against the live source, and enforces at least one video and
  one audio track kept and at most one default per audio/subtitle type
  (`Weir.Core.Refiner.ManualTrackPlan.TryValidate`). On success it enqueues a
  `refiner.file.remux_pass.v1` job carrying the choice and fingerprint, and records
  `refiner.file_manual_plan_queued` with the actor. The file's own status is left alone (`on_hold`),
  which already reads as `queued` on the hand-off ledger (`HandoffLedgerRules.FileState`) the moment
  a job exists for it, and as `working` once the worker claims it — so held → queued → working needs
  no new state, only the existing ledger mapping.
- **In the pass** (`RemuxPassRunner.RunInnerAsync`), a manual plan re-probes the source and checks
  the fingerprint taken at submission against the one taken now, plus every chosen index against a
  fresh classification of the live streams (`ManualTrackPlan.ClassifyIndices`). Either kind of
  mismatch — the file changed, or an index no longer exists or changed type — fails with the same
  sentence: "The file changed since you chose its tracks; choose again." Otherwise
  `ManualTrackPlan.BuildPlan` builds the `RemuxPlan` directly from the choice, skipping `PlanRemux`
  entirely (no candidate ranking, no name-derived flags, no metadata stripping) — the precedent this
  issue names is muxarr's `CustomConversionEditor`/`ConversionPlan`, where a custom plan is
  authoritative and the automatic mutations do not apply; the owner cleared following that
  precedent. Normal output validation, collision handling and cleanup run unchanged afterward.

## Library mode (#505)

`Weir.Infrastructure/LibraryMode` (`LibraryScanHandler`, `LibraryCleanHandler`) and `Weir.Api/Endpoints/LibraryModeEndpoints` let Weir clean files already in a library, in place, on its own — separate from the download pipeline (watched folder → remux → output folder → manager import), which is unchanged. New surface: there is no Python router or model to port.

### Storage decision

Library mode was built while ADR-0017 froze the SQLite schema, so its state is stored on `refiner_jobs` rows rather than new tables, the same approach `RefinerJobSwapJournal` (#506) uses. The freeze ended with #523; this state can move to proper tables in a later migration.

- **`library_folders` / `library_schedule_enabled`** (`Weir.Core.LibraryMode.LibrarySettings`): one permanent row per library, `job_kind = "refiner.library.settings.v1"`, dedupe key `…:{library_id}`, status always `completed` so no worker ever claims it. Written with a plain `INSERT … ON CONFLICT(dedupe_key) DO UPDATE` (`LibrarySettingsStore`), not `RefinerJobStore.EnqueueOrGetAsync` (which always inserts a fresh `pending` row). Excluded from the Jobs page's default "recent" listing (`JobsInspectionStore`) the same way completed watched-folder scan-dispatch rows already are, so an idle settings row never looks like a stuck job.
- **The file index / plan cache**: not a separate cache at all — the *latest completed* `job_kind = "refiner.library.scan.v1"` row for a library **is** the cache. Each scan request is an ordinary job (a fresh dedupe key per request, `…:{library_id}:{guid}`), so it is visible in the Jobs page like any real work; its completed `payload_json`'s `scan_result` key holds every file's classification and its raw ffprobe JSON, keyed by path, size and mtime for reuse on the next scan. `LibraryScanStore` reads/writes it directly with parameterised SQL (`dedupe_key LIKE '{prefix}%'`), never SQLite's JSON1 functions, to avoid depending on a build option.
- **Clean jobs** (`job_kind = "refiner.library.clean.v1"`, dedupe key `…:{library_id}:{sha256(path)}`) are ordinary, real jobs: one per file, claimed, run and completed exactly like a download-pipeline job.
- Deleting a library deletes its settings and scan-history rows (`LibrarySettingsStore.DeleteAllForLibraryAsync`, called from `RefinerLibraryEndpoints.DeleteLibraryAsync`).

A real table was **not** chosen at the time because the schema was frozen and `SchemaParityTests` required the .NET migrations to match the Alembic head exactly. Now that the .NET migrations are the only schema source, moving this state into its own tables is an ordinary migration.

### Processing flow

1. **Scan** (`LibraryScanHandler`, read-only): loads the library's rules exactly as the download pipeline would (`RemuxPassPaths.RulesConfigFor` / `RuleSetConversion.ToRulesConfig`), walks its library folders (`LibraryFileWalker`, honouring the library's own extension/exclude-marker/hidden/top-level-only settings), and for each file either reuses the previous scan's cached ffprobe JSON (path, size and mtime all match) or probes it fresh. `Weir.Core.LibraryMode.LibraryFilePlanner.Classify` runs `RemuxRules.PlanRemux` / `IsRemuxRequired` — the same engine the remux pass plans with — to decide **matches** / **would change** (with a summary and a lower-bound size-saved estimate from the removed tracks' own ffprobe bit rate) / **cannot process** (no video track, ffprobe failed, or no audio would survive the plan). A scan never writes to a file it looked at (proved in `LibraryScanHandlerTests`).
2. **Clean** (`LibraryCleanHandler`, one job per file): re-probes and re-plans the same way (so a stale scan cache can never cause a clean the current rules would not also produce), then — only when the plan actually changes something and, if it removes any track, `confirm_final_removal` was set on the job's own payload — remuxes to a temp file via `MediaTools.RemuxToTempFileAsync` (mirroring the remux pass's own call) and hands it to `SafeSwap.RunAsync` with `RemuxOutputSwapValidator` (below) as the output check. On a committed swap it calls the `ILibraryFileChangeNotifier` seam (#507, below) and records `library.file_cleaned`; on anything else short of a commit it records `library.file_failed` or `library.file_skipped` and leaves the original untouched. It never calls `IFailurePolicy`: no code path here can queue `refiner.file.reject.v1` or `refiner.file.pass_through.v1` (`LibraryCleanHandlerTests.A_library_failure_never_queues_a_reject_or_pass_through_job` proves it, including through the generic unhandled-job-failure path — the payload's file-path field is named `path`, not `relative_media_path`, so `RemuxPassFailureRecorder` finds nothing to act on for a library job even on an unhandled exception).
3. **The `#500` output validator seam**: `RemuxOutputSwapValidator` (an `ISwapOutputValidator`) is what plugs into `SafeSwap` here, since the #500 output-check pipeline referenced throughout this README is not in this codebase yet. It runs the same full-read integrity check the download pipeline already ships (`MediaTools.ValidateMediaIntegrityAsync`), cross-checked against the original's re-probed duration. `ISwapOutputValidator` is the only thing `SafeSwap` depends on, so #500's richer per-track checks can replace this in place later.
4. **A locked file** (`SwapOutcome.InUse`) is not treated as a job failure: `LibraryCleanHandler` puts its own row back to `pending` with `not_before` set from `SafeSwapRules.InUseRetryDelay` (5, then 15, then 60 minutes) and clears its own lease, so `RefinerJobStore.CompleteClaimedAsync`'s lease check finds nothing to complete and leaves the requeue alone. After the third attempt it reports `SafeSwapRules.InUseGaveUpMessage` and lets the job complete normally.
5. **Queueing behind downloads**: every library job (scan and clean) is enqueued at `Weir.Core.LibraryMode.LibraryModePriority.Low` (a large negative number). `refiner_jobs` claims `ORDER BY priority DESC, id ASC`, and a stuck download job's priority is only ever bumped *upward* (`max(pending) + 1`), so a library job can never be claimed ahead of a pending download-pipeline job, however long either has waited (`LibraryCleanHandlerTests.Library_jobs_are_claimed_behind_a_pending_download_job`).

### API (`Weir.Api/Endpoints/LibraryModeEndpoints`)

- `GET`/`PUT /refiner/libraries/{id}/library-settings` — the folders and schedule flag. `PUT` validates with `Weir.Core.LibraryMode.LibraryFolderRules.Validate` (reusing `LibraryRules.NormalizeFolder`/`FoldersOverlap`), refusing a folder that overlaps the library's own watched/work/output folders; it does **not** check overlap with another library's or a manager's folders, since #505 explicitly allows sharing those.
- `POST /refiner/libraries/{id}/library-scan` — enqueues a scan (or returns the one already running).
- `GET /refiner/libraries/{id}/library-files` — the latest scan's files, filtered by `classification`, `manager` or a path search `q`, with the removal/size summary the confirmation dialog needs.
- `POST /refiner/libraries/{id}/library-files/clean` — cleans the selected paths; refused with `400 {"error":"confirm_final_removal_required", "detail": "<the exact sentence>", "files_count", "tracks_count", "estimated_bytes_saved", "warnings": []}` when any selected file would lose a track and `confirm_final_removal` was not sent.
- `POST /refiner/libraries/{id}/library-schedule` — turns library mode's own schedule flag on or off (reusing the library's *existing* schedule window/grid — there is no second schedule to configure); turning it on for the first time needs the same confirmation as Clean, using the latest scan's numbers.
- Saving a rule set (`PUT /refiner/rule-sets/{id}`) enqueues a background rescan (`trigger: "rule_change"`) for every library that uses it and already has library folders configured — never a clean. The web reads the result back through `GET .../library-files`.

### Seams for #507, #508 and #509

- **`ILibraryFileChangeNotifier`** (`Weir.Core/MediaManagers/LibraryFileChangeRules.cs`) is #507's interface (`LibraryFileChange`, the notifier, and its pure rules). `LibraryCleanHandler` calls it once per committed swap; the live registration is `Weir.Infrastructure.MediaManagers.LibraryFileChangeNotifier` (from `AddWeirMediaManagers`), which tells every Sonarr/Radarr/Deluno connection that owns the changed file to re-read it, retrying transient failures before recording a warning. The two branches were developed against slightly different copies of this seam; only #507's is kept — see its own "Notify media managers after a library-mode file swap" section below.
- **Manager title matching** ("Blade Runner 2049 (Radarr)", issue #551) uses the same `ListLibraryFilesAsync` port extension #507 adds. During a scan, `LibraryScanHandler` calls it once per enabled connection covering the library's media scope, then matches each manager file to one of its own walked paths with `Weir.Infrastructure.MediaManagers.LibraryTitleMatcher.MatchLocalPath` — a direct path comparison first (Weir and the manager share paths, the common case), then the reverse of `HandoffCompletionReporter.TranslateOutputPath` (the same local-&gt;manager substitution #507's notify step already uses, run the other way: a manager's own file path rebuilt under one of the library's local folders) through every pairing of the manager's own library roots (from `DescribeAsync`) and the library's local folders. The match — `manager_connection_id`, `manager_kind`, `title_id`/`title_name` and the manager's own file id and quality profile id (read from the same movie/series payload the match already parsed, so no extra call) — is stored on the scan's own `LibraryScanFileEntry` (still inside the frozen `refiner_jobs.payload_json`, no schema change). A manager `ListLibraryFilesAsync` reports unreachable is recorded as a scan error ("Weir couldn't ask Radarr which titles it manages: ...") rather than failing the scan; every file it would have covered, like any file no connection claims, stays unmatched and processable (#505 explicitly allows this).
- **#508 (seeding / re-download-risk warnings)**: `Weir.Core.LibraryMode.HardlinkPolicy`/`LibraryCleanPreflight` and two new per-library settings, `clean_hardlinked_files` (default false) and `skip_if_manager_would_redownload` (default true), are wired into `LibraryCleanHandler` and the `library-files/clean`/`library-schedule` endpoints: a file another name still shares data with is skipped, and never queued even when the removal is confirmed, unless the library opts in. `ConfirmationRequired`'s `warnings` array is populated from the same preflight, run at request time over the selected/scanned files (a scan can be stale). The re-download-risk half (`RedownloadRiskEvaluator`/`RedownloadRiskChecker`) now runs too, for any file #551's title matching resolved to a Sonarr/Radarr title with something being removed: the match's own file id and quality profile id are exactly what `RedownloadRiskChecker.CheckAsync` needs, and the removed audio languages are re-derived from the file's cached ffprobe JSON (`LibraryModeEndpoints.RemovedAudioLanguages`, the same replan `LibraryCleanHandler` runs before touching the file) since the scan's plan cache keeps only a count.
- **#509 (re-download after a rule change)**: `LibraryCleanHandler` records a committed clean's `RemovedTrackRecords` (via `IRemovedTrackStore`, the durable `FileLogRemovedTrackStore`), keyed by library id and path. `GET /refiner/libraries/{id}/library-redownloads` runs `RemovedTrackDiff.AffectedFiles` against the library's current rules and every recorded removal to answer "N titles are missing tracks your new rules keep"; `POST` on the same path is #509 step 3's "Download again", gated on `confirm_destructive`. Both endpoints are fully wired to `IManagerRedownload`/`ManagerRedownloadRules`: `can_redownload` (`ManagerRedownloadRules.CanRedownload`) is true for a manager kind #509 verified (Sonarr/Radarr) whose scan actually matched the file to one of that manager's titles, and `POST` resolves the same match's connection and title id to make the real call, answering `unsupported` (no match, or a manager kind #509 does not verify) or `failed` (the manager call itself could not be reached) otherwise.

### Web

`apps/web/src/pages/refiner/refiner-library-section.tsx` (a new "Library" tab on the Refiner page): library folders (add/remove, saved via `PUT .../library-settings`), the schedule On/Off toggle, two #508 preflight checkboxes (`clean_hardlinked_files`, `skip_if_manager_would_redownload`, saved the same way), a "Scan now" button, and the file table (classification/manager/search filters, per-file summary, multi-select, "Clean selected", a post-clean notice for any file skipped or warned about). `apps/web/src/components/refiner/library-removal-confirmation-dialog.tsx` renders the exact required sentence — "N files, M tracks will be removed. Removed tracks are gone for good; getting one back means downloading the title again." — plus the estimated size saved and #508's preflight warnings, shared by Clean and by turning the schedule on. A "Titles missing tracks your new rules keep" section (#509) lists each title's removed tracks with a "Download again" button, shown only when the API says `can_redownload`, that renders `ManagerRedownloadRules.DestructiveConfirmation`'s exact wording before confirming. `apps/web/src/lib/refiner/library-api.ts` treats the `confirm_final_removal_required` 400 as a normal, typed outcome (not a thrown error), so the caller decides whether to show the dialog. New OpenAPI paths/schemas were hand-added to the committed `apps/web/openapi/weir-openapi.json` (`npm run api:types:generate` regenerates the TS types from it, and `api:types:check` — generate, then diff — is the gate that keeps them in sync). `npm run api:openapi:export` (Python's FastAPI app introspection) is a separate, no-longer-wired-into-`sync`/`check` script that would overwrite this file with only the Python side's routes; library mode has none there, so its OpenAPI entries stay hand-written.

### Tests

`Weir.Core.Tests/LibraryMode` (`LibraryFilePlannerTests`, `LibraryModeSettingsTests`) cover classification and folder/JSON rules in isolation. `Weir.Infrastructure.Tests/LibraryMode` (`LibraryScanHandlerTests`, `LibraryCleanHandlerTests`) run both handlers against a real database and real files behind a fake ffmpeg/ffprobe process runner: a scan never writes to a file; clean is refused without confirmation; a library failure never queues a reject or pass-through job; library jobs are claimed behind a pending download job; an unmatched file still processes; and a full clean commits the swap and leaves no temp/backup leftovers. Issue #551's title matching is covered in the same file, behind a scripted Sonarr/Radarr connection (`Weir.Infrastructure.Tests.MediaManagers.MediaManagerFixture`/`FakeManagerHttp`): a shared path matches directly, a differing manager library root matches through the reverse path translation, an unreachable manager is recorded as a scan error with the file left unmatched, and the scan's own match data (connection, file id, quality profile id) is fed straight into `RedownloadRiskChecker`/`LibraryCleanPreflight` to prove the #508 warning is real for a matched file. `ManagerRedownloadRules.CanRedownload` (#551/#509's `can_redownload` gate) is covered in `Weir.Infrastructure.Tests.MediaManagers.ArrManagerRedownloadTests`. `apps/web/src/pages/refiner/refiner-library-section.test.tsx` covers the file list rendering, the manager filter and the confirmation dialog's exact text end to end. No contract-suite scenario was added: the Python-driven contract suite has no library-mode surface to exercise against a running server of either backend.

## Output ownership (#555)

`Weir.Infrastructure.Refiner.OutputOwnership` (registered by `WeirPlatformServices.AddWeirPlatform`,
so every area that publishes a file already has it) applies the optional `WEIR_CHOWN_OUTPUT` /
`WEIR_FILE_MODE_OUTPUT` / `WEIR_DIR_MODE_OUTPUT` policy directly to a file Weir just published, or a
folder it just created to publish into — not as a recursive startup sweep, the way the retired
Python backend's `weir.platform.docker_runtime` module used to chown/chmod the watched/work/output
folders named in Refiner settings once, at container start, before it was deleted with the rest of
the Python backend in #523.

- **Settings** (`WeirOptions`/`WeirOptionsLoader`, `Weir.Core.Configuration`): `OutputOwnershipChownEnabled`
  (`WEIR_CHOWN_OUTPUT`, default off); `OutputOwnershipUid`/`OutputOwnershipGid` (the first non-blank of
  `WEIR_PUID`/`PUID` and `WEIR_PGID`/`PGID`, default 1000 each — the same variables the Docker
  entrypoint uses to remap the container's own runtime user, so a chowned output file matches the
  identity Weir itself runs as); `OutputOwnershipFileMode`/`OutputOwnershipDirectoryMode`
  (`WEIR_FILE_MODE_OUTPUT`/`WEIR_DIR_MODE_OUTPUT`, octal strings such as `664`/`775` or the
  setgid form `2775`, parsed straight into `System.IO.UnixFileMode` — an *n*-digit octal string's
  own bits already line up with that enum's flags, so `(UnixFileMode)Convert.ToInt32(value, 8)` is
  exact). A malformed octal mode refuses to start with a clear message, the same way
  `WEIR_CORS_ORIGINS=*` does; an unset value is `null` and changes nothing.
- **`IOutputOwnership`** (`ApplyToFile`/`ApplyToDirectory`) is called from the existing
  publish/finalize points: `Weir.Infrastructure.Refiner.RemuxPass.FileLifecycle`'s
  `SafeCopyToFinalAsync`/`TryHardlinkToFinalAsync`/`SafeFinalizeFile` (an optional `ownership`
  parameter, applied to the destination directory right after it is created and to the file right
  after it is published) cover the remux pass's own publish and `PassThroughDelivery.DeliverUnchangedAsync`
  in one place, and `Weir.Infrastructure.LibraryMode.SafeSwap.RunAsync` calls it directly after the
  commit rename that exposes the cleaned copy under the original name. `WEIR_CHOWN_WATCHED`/
  `WEIR_CHOWN_TEMP`/`WEIR_DIR_MODE_WATCHED`/`WEIR_DIR_MODE_TEMP` (the Python backend's other two
  folder categories) have no .NET equivalent and are not planned: the watched and work folders are
  never something Weir itself just wrote, so there is nothing for a "just published this" hook to
  attach them to.
- **Linux only, by design, not by omission.** `IOutputOwnershipTools` (`Chown`/`SetMode`) is the
  seam: `LinuxOutputOwnershipTools` calls a libc `chown` P/Invoke (the same shape as
  `LibraryMode.PhysicalSwapFileSystem`'s permission copy) and `File.SetUnixFileMode`;
  `WindowsOutputOwnershipTools` does nothing. `AddWeirPlatform` chooses between them once, by
  `OperatingSystem.IsWindows()`, and — only when an operator actually set one of the three
  settings — logs a warning once at startup on Windows rather than silently doing nothing forever.
  `OutputOwnership` itself never branches on platform; it only calls whichever tools it was given,
  which is what lets `OutputOwnershipTests` prove its chown/mode decision logic (when to call which,
  that a tool failure never propagates) on any OS, off a fake `IOutputOwnershipTools`.
  `LinuxOutputOwnershipToolsRealFilesystemTests` proves the real P/Invoke and `SetUnixFileMode`
  calls against real files, gated to Linux (skipped elsewhere with a reason) since neither exists
  off it; its chown case only ever chowns a file to the running process's own uid/gid, since
  chowning to an arbitrary uid needs root and the point is to exercise the syscall, not to require one.
- **A failure here never fails the job.** `OutputOwnership.Apply` catches every exception from
  `IOutputOwnershipTools` and logs a warning — a chown that fails because Weir is not root, or a
  mode Weir cannot set on a network share, must not undo a remux, pass-through or library swap that
  already succeeded.

## Activity

`Weir.Api/Endpoints/ActivityEndpoints` ports `weir.platform.activity.router`: `recent` (filters, `before_id` paging), `export` (CSV and JSON), `file-history` and its removal, and the `stream` of `activity.latest` frames. The SQL in `Weir.Infrastructure/Activity/ActivityHistoryStore` is the text SQLAlchemy compiles, clause for clause, except for four defects found while porting and fixed here (issue #543; Python keeps all four, so the byte-for-byte comparison in `ActivityHistoryStoreTests` skips the cases that touch them):

1. **`total`/`has_more`.** Python's count query loses its `FROM` when there is no filter (`SELECT count(*)`, which counts one row); `CountAsync` always counts from `activity_events`.
2. **Date filters.** Python compares `date_from`/`date_to` as raw text against the stored column, so a query offset is ignored and a row stored without its `.000000` (an exact second) can sort as earlier than the same instant with one, wrongly excluding it. `Where` normalizes the query value to UTC and compares with `julianday()`, which parses both stored shapes to the same instant.
3. **Paging order.** `ListRecentAsync` orders by `(created_at DESC, id DESC)`, a total order that no longer depends on which plan SQLite picks for a tie (the previous unary-plus hint kept .NET's SQLite 3.53 choosing the same plan as Python's 3.45 for that reason alone). `before_id` pages by that same key — everything strictly after the cursor row — instead of by id alone, so a row tied on `created_at` with the cursor is never skipped or repeated the way Python's id-only paging can.
4. **File-history removal.** Python's `_file_history_filter` (Activity events) also matches a row that never recorded a library id, but `_processing_records` does not, so removing one file's history with a library id could leave its processing records behind. `ProcessingRecordsClause` now gets the same null fallback as `FileHistoryClause`.

Writers never notify listeners directly. `SqliteActivityWriter` records the ids it wrote on the unit of work or raw transaction, and `ActivityNotifications` tells the database's `ActivityLatestNotifier` after the commit (a rollback tells nobody). Code that commits its own raw transaction after `SqliteActivityWriter.Record` calls `ActivityNotifications.TransactionCommitted`, as `RefinerJobStore.InTransactionAsync` does. `RefinerFileLogRetentionTask` prunes processing records hourly by `file_log_retention_days`.

## Publish and packaging

Self-contained single-file builds for `win-x64`, `linux-x64` and `linux-arm64`, through the checked-in profiles in `src/Weir.Host/Properties/PublishProfiles`:

```powershell
dotnet publish apps/server/src/Weir.Host -p:PublishProfile=win-x64       # apps/server/artifacts/publish/win-x64/Weir.exe
dotnet publish apps/server/src/Weir.Host -p:PublishProfile=linux-arm64
```

Always publish through a profile, never with `-r`/`--self-contained`/`-p:PublishSingleFile=true` on the command line: a command-line `PublishSingleFile` is a global property that reaches every project, and the single-file analyzer then fails `Weir.Infrastructure` with IL3000 on the `Assembly.Location` check that detects single-file mode on purpose (`SystemServices.DetectInstallType`, `MediaToolResolver.ForCurrentProcess`). The profiles scope those properties to `Weir.Host`.

A single-file publish is .NET's equivalent of a frozen build: `MediaToolResolver` then also looks for ffmpeg and ffprobe in `<app>/bin/ffmpeg`, after `WEIR_FFMPEG_DIR` and `<WEIR_HOME>/bin/ffmpeg` and before `PATH`.

The product version is `WeirVersion` in `Directory.Build.props`; the assembly version, `--version`, `/openapi.json` and the packages all take it from there.

- **Docker** (`Dockerfile`, `docker/entrypoint.sh`, `compose.yaml`, [`docker/README.md`](../../docker/README.md)): the SDK stage runs on the build machine's architecture and cross-publishes `linux-x64` or `linux-arm64` (no emulation needed for the .NET build); the final stage is `mcr.microsoft.com/dotnet/runtime-deps:10.0-bookworm-slim` with ffmpeg, curl and gosu, user `weir` (UID/GID 1000), `/opt/weir/Weir`, `/opt/weir/web-dist`, the `/data/weir` volume, port 8788 and a `/health` healthcheck. The entrypoint has no migration step (the server migrates its own database) and generates the persisted session secret with coreutils. Releases publish `linux/amd64` and `linux/arm64`.
- **Windows** (`packaging/windows/build-velopack.ps1`): builds the web app, publishes the server with the `win-x64` profile, smoke-tests the raw publish, publishes the tray app, and packs `dist/windows/pack` with Velopack (`--packId Weir --mainExe Weir.exe`): the tray at the root, the server renamed to `server/WeirServer.exe` (its assembly name `Weir` would collide with the tray's `Weir.exe`), `server/web-dist` and `server/bin/ffmpeg`. `scripts/smoke-windows-package.ps1` then starts `server/WeirServer.exe` the way the tray does, with ffmpeg removed from `PATH`, checks it finds its bundled ffmpeg and runs a real pass-through job.
