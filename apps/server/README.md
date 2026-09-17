# Weir server (.NET)

The C# / .NET 10 backend that replaces the Python backend in `apps/backend`, area by area, without changing the HTTP API, the web app or the SQLite schema. Why and how: [ADR-0017](../../docs/adr/ADR-0017-backend-on-dotnet.md). Until the switch (#523), `apps/backend` is the reference and the shipped server.

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

It reads the same `WEIR_*` environment variables as the Python backend, with the same defaults (see `apps/backend/.env.example`). It does not read `apps/backend/.env`.

```powershell
$env:WEIR_HOME = "$env:TEMP\weir-dotnet"          # optional; defaults to %PROGRAMDATA%\Weir
$env:WEIR_WEB_DIST = "$PWD\apps\web\dist"          # optional; after `npm run build` in apps/web
dotnet run --project apps/server/src/Weir.Host -- --host 127.0.0.1 --port 8788
```

`--port` (what the Windows tray passes) wins over `PORT` (what the Docker entrypoint sets); both default to 8788 on every interface.

On startup the server creates an empty database at the current schema, opens a database already at Alembic head `0036_drop_pruner_tables` without changing it, and refuses anything else with a message. It records its version in Alembic's own `alembic_version` table, so either backend can open a database the other created.

## Schema parity

`tests/Weir.Infrastructure.Tests/schema/alembic-head.sql` is the schema and seed rows that `alembic upgrade head` creates. The parity test builds a database from it and one from the .NET migrations and compares tables, columns, types, defaults, keys, indexes, foreign keys, SQL text and rows. After an Alembic change, regenerate it with the backend's virtualenv:

```powershell
apps/backend/.venv/Scripts/python.exe scripts/dump-alembic-schema.py          # write
apps/backend/.venv/Scripts/python.exe scripts/dump-alembic-schema.py --check  # CI runs this
```

## Rules parity

`Weir.Core.Rules` is a port of Refiner's rules engine (`refiner_remux_rules.py`, `refiner_track_sorters.py`, `refiner_metadata_rules.py`, the pure parts of `refiner_original_language.py` and the display helpers). `tests/Weir.Core.Tests/Rules/golden/*.json` hold ffprobe-style inputs with the plan, notes and display lines the Python engine produced for them; `GoldenParityTests` requires the same answers. After a change to those Python modules, regenerate them with the backend's virtualenv:

```powershell
apps/backend/.venv/Scripts/python.exe scripts/generate-rules-golden.py          # write
apps/backend/.venv/Scripts/python.exe scripts/generate-rules-golden.py --check  # compare only
```

### Golden overrides (deliberate divergence from Python)

Issue #537 fixed defects in the rules engine that the golden corpus had pinned as "today's behaviour" (its items 1, 2, 3, 5 and 6 — see the issue for each one). `apps/backend` is being retired (ADR-0017) and is not touched to "fix" these in Python, so regenerating the golden files from Python would just re-record the same bugs. Instead, a case whose correct answer now differs from Python's recorded one gets a same-named file in `tests/Weir.Core.Tests/Rules/golden/overrides/`, holding the issue number, which item(s) of it, and the new expected output, e.g.:

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
- **Issue #495 (track flags from names) is engine-only so far.** `Weir.Core.Rules.TrackFlagsReader.Detect` and the new `RefinerRulesConfig.RemoveHearingImpairedSubs` field are wired into `RemuxRules.PlanRemux` (subtitle forced/hearing-impaired handling, audio commentary/dub/audio-description). Persisting the new setting, exposing it over the API, and the web checkbox are not in scope here — they wait on the settings/refiner-config API port that is already in flight.
- **Issue #497 (keep one audio track per language; cap subtitles per language) is engine-only so far.** `RefinerRulesConfig.AudioKeepMode` (`single`, the default and today's behaviour, or `per_language`), `SubtitleMaxPerLanguage` (0 = unlimited, the default) and `SubtitleQualityStrategy` (`text_first`, the default, `image_first` or `accessibility`) are wired into `RemuxRules.PlanRemux`: `per_language` keeps the best track (by the configured sorters, variant-aware via `LanguageVariants.Matches`) of each configured language slot that has one, in slot order, with `DefaultAudioSlot` (primary by default) marking the default track, and never keeps zero audio; the subtitle cap groups matched candidates by the language slot they matched, exempts a track kept under `PreserveForcedSubs`, and otherwise keeps the best `SubtitleMaxPerLanguage` per group by format (text over image, or the reverse under `image_first`) then type (regular over SDH over forced, or SDH first under `accessibility`), noting every drop with a reason. A migration, the settings/refiner-config API, and web controls for these three fields are not in scope here — see `Issue497Tests` for the behaviour and `GoldenParityTests` for proof that `single` mode and an unlimited cap (both defaults) still behave exactly as before.
- **Issue #496 (regional language variants) is engine-only so far.** `Weir.Core.Rules.LanguageVariants.DetectVariant(title, baseCode, bcp47Tag)` tells apart Quebec/France/Belgium French, Castilian/Latin American Spanish, Brazilian/European Portuguese, Traditional/Simplified Chinese, Cantonese, Mandarin and Flemish from a track's name or an explicit BCP 47 region/script subtag. An identifier is `{base}-{REGION}` (`fre-CA`, `por-BR`), `{base}-{region}` with a UN M49 region (`spa-419`), `{base}-{Script}` (`zho-Hant`, `zho-Hans`), or a bare ISO 639-3 code offered as a refinement of a macrolanguage (`yue`, `cmn`); `base` is a fixed canonical spelling per entry, not necessarily the input tag's own spelling. Detection is refine-only: an explicit region/script subtag is read directly and never overridden by the name; a self-identifying marker (`VFQ`) works on an undetermined track or one whose base language already agrees, but never on a conflicting one; a refine-only marker (bare `Latino`, `Europeu`, `Traditional`) only ever applies once the base language already agrees. `RemuxRules.PlanRemux` computes it for every audio and subtitle candidate and matches it against `PrimaryAudioLang`/`SecondaryAudioLang`/`TertiaryAudioLang` and `SubtitleLangs` (via `LanguageVariants.Matches` and `NormalizeLanguageOrVariant`): a plain base value (`"fre"`) still matches every variant, unchanged; a variant value (`"fre-CA"`) matches only that exact variant. A detected variant on the selected audio track adds a plan note (`"French (Canada), from the track name 'VFQ'."`). Persisting a variant-aware audio/subtitle preference, exposing it over the API, and a web language picker that lists variants under their base language are not in scope here — see `LanguageVariantsTests` for the detection table and the wiring, and `GoldenParityTests` (585 pre-existing cases, unchanged) for proof that a plain-language rule still behaves exactly as before.

## ffmpeg parity

`Weir.Core.Media` ports the decisions in `refiner_remux_mux.py` and `refiner_hardware_acceleration.py`: ffprobe and ffmpeg command lines (token for token), unreadable-media classification, output and duration validation, progress parsing and hardware choice. `Weir.Infrastructure.Media.MediaTools` runs the tools through `IProcessRunner` (`ProcessRunner` kills the whole process tree on timeout or cancellation). `tests/Weir.Core.Tests/Media/golden/*.json` record what the Python functions did with their processes replaced by recorded inputs, including log payloads and exception messages; `MediaGoldenParityTests` and `MediaToolsGoldenTests` require the same. Regenerate after a change to those Python modules:

```powershell
apps/backend/.venv/Scripts/python.exe scripts/generate-ffmpeg-golden.py          # write
apps/backend/.venv/Scripts/python.exe scripts/generate-ffmpeg-golden.py --check  # compare only
```

`RealFfmpegTests` run real ffprobe and ffmpeg on files generated with `-f lavfi`. They skip unless the tools are found through `WEIR_FFMPEG_DIR` or `PATH`; on Windows, point `WEIR_FFMPEG_DIR` at a packaged build's `_internal/bin/ffmpeg`.

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

## Jobs and workers

The durable queue is the Python backend's `refiner_jobs` table, used the same way: the same statuses, dedupe keys, claim statement, lease checks, retry backoff and failure wording, and the same timestamp text, so either backend can claim, finish or recover a row the other wrote (`tests/Weir.Infrastructure.Tests/Jobs/CrossBackendTests.cs` proves it against the Python code when `apps/backend/.venv` exists, or `WEIR_TEST_PYTHON` names an interpreter with the backend's dependencies; the cross-checks always import this checkout's `apps/backend/src`).

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
- **#531 item 2 (remainder).** The origin-carry fix already covers pass-through and reject: since both are enqueued with whatever origin the caller resolved (carried by `HandoffOriginCarry` beforehand, or attached directly), their own completion/rejection report always has an output path or a disposition to send.
- **#539 / #494 end to end.** A zero-filled `.mkv` under the `reject` policy now genuinely rejects: unreadable-media classification (#539 item 1, already fixed in the ffmpeg layer) triggers `reject_bad_release` inside `RemuxPassHandler`, which queues `refiner.file.reject.v1`; the handler above then reports the Deluno hand-off `failed` with `disposition: rejected` — proven by `RefinerRejectHandlerTests` and the reject-through-handoff path, never `completed` with a copy.

## Library mode: safe swap (#506)

`Weir.Infrastructure/LibraryMode` replaces a library file with its cleaned copy so that a crash, power cut, locked file or concurrent change can never lose it or overwrite a newer one. It is .NET only (no Python counterpart) and not wired into a job yet: the library-mode job flow (#505) calls `SafeSwap.RunAsync` with a writer (ffmpeg) and an `ISwapOutputValidator` (the #500 output checks), and runs `SwapRecoverySweep` at startup before any worker. The pure rules (names, space margin, in-use backoff, wording) are in `Weir.Core/LibraryMode/SafeSwapRules`.

- **Preflight:** the file exists; its link count is 1 (else skipped as seeding, unless the library allows hardlinked files); the volume has the file's size plus 1 GiB free; a probe file can be written beside it; it is not read-only; no other program holds it; its fingerprint (`SourceFiles.Fingerprint`, as the remux pass) is recorded.
- **Write and check:** `<name>.weir-tmp<ext>` beside the original, then the validator.
- **Commit:** re-fingerprint (changed → discard, "The file changed while Weir was working; nothing was replaced"); copy permissions (Windows DACL; POSIX mode bits, and owner when root; never the mtime); rename original → `<name>.weir-bak<ext>` and check the backup is still the fingerprinted file; rename temp → original name (the commit); record it; delete the backup (a failure is logged and left for the sweep).
- **Renames** are same-folder and never replace an existing file: `MoveFileExW` with only `MOVEFILE_WRITE_THROUGH` on Windows (no replace, no copy fallback), `File.Move(overwrite: false)` elsewhere.
- **Rollback and sweep** judge from the files alone: backup present and original missing → rename it back; backup and original present → delete the backup; temp → delete. A locked file (sharing violation, `EBUSY`) is the `InUse` outcome, requeued after 5, 15 and 60 minutes (`SafeSwapRules.InUseRetryDelay`).
- **Persistence:** progress is recorded on the job row, not in a new table, because ADR-0017 keeps the SQLite schema fixed until the switch (#523). `RefinerJobSwapJournal` adds `library_swap` (`state`: `writing`, `committing`, `committed`, `finished`, `rolled_back`, `recovered`, plus the three paths) and `swap_committed: true` to `refiner_jobs.payload_json`, keeping every other key. The sweep visits the paths of unfinished swaps first; walking library folders is a fallback. No migration and no schema-parity change.
- **Tests:** `SafeSwapTests` injects a failure, a failure after the effect, a crash and a crash after the effect at every one of the swap's 23 filesystem and journal operations and proves exactly one intact file remains (original content before the commit rename, cleaned content after), with the journal alone enough to recover every crash. `PhysicalSwapTests` run the swap and sweep on real files and a real job row, including a file held open by another handle.
### Fixed in #545

Defects the .NET port kept parity with while porting the remux pass (#522 part 3); fixed here, after the switch-over, so `apps/backend` is not touched.

1. **Output-folder cleanup could delete a folder before a manager imported it.** `LibraryTruthGate.EvaluateForFolder` used to clear a folder for deletion whenever every reporting manager had no *conflicting* file sitting inside it — which is exactly what a manager that has not scanned or finished importing yet (or one that imports by copy and scans later) looks like. It now also requires positive evidence the release was picked up: a manager's own reported library names this exact output path anywhere (not only inside the folder), or the same title (file-name stem) at a different path, which is how a manager that renames or reorganises on import records it — or the hand-off ledger already recorded this pass's outcome as `completed`/`passed-through` (`IPostSuccessCleanupData.HandoffOutcomeAcknowledgedAsync`). Absent either, the folder is left in place regardless of age. The existing movie/TV output-cleanup minimum-age settings (`WEIR_REFINER_MOVIE_OUTPUT_CLEANUP_MIN_AGE_SECONDS` / `..._TV_...`, floored at one hour) double as the manager's import window: nothing is ever removed before that age, confirmed or not. `tests/contract/processing/test_output_folder_cleanup.py` proves it end to end with a fake Radarr that reports an empty library (`known_bug(issue=545, backends=("python",))`, since the Python reference still has this bug) and a companion test proving the folder is removed once the manager confirms the import.
2. **Pass-through and reject jobs deduped forever.** Their dedupe key was `{kind}:{library}:{path}` alone, so once one finished, a later failure of a replaced file (e.g. a re-download with the same name) never queued another. `QueueingFailurePolicy.FingerprintTag` (built on `SourceFiles.DedupeFingerprintTag`: size and modification time) is now folded into the key, so a changed file gets a fresh key while a repeat enqueue for the same, unchanged file still dedupes against the row already there. `HandoffLedgerStore.JobsForAsync` matches the base key as an exact match or a prefix, so the ledger keeps finding these jobs regardless of the fingerprint suffix.
3. **An undelivered pass-through or reject reported nothing.** Once such a job exhausted its own retries it dropped out of `JobsForAsync`'s pending/leased filter and vanished from the hand-off status API. `JobsForAsync` now also returns a `failed`-status row for these two job kinds, and `HandoffLedgerStore.CurrentStatusAsync` reports a pending one as `scheduled` (never `queued` — that field means the remux queue, not a decided disposition about to run) or `working` while leased, and a permanently failed one as `failed` with the job's own `last_error` as the reason.
4. **Stored subtitle mode wasn't normalized on both rule-config paths.** `RemuxPassPaths.RulesConfigFor` (the live pass) used to pass the stored mode through unchanged, while `RuleSetConversion.ToRulesConfig` (the rule-less fallback) normalized it. Both now call `RuleSetConversion.NormalizeSubtitleMode`.
5. **Measured media facts and collision decisions landed on every library's row.** `RemuxPassFileState.RecordMeasuredMediaFactsAsync` and `RecordOutputCollisionAsync` matched on `relative_path` alone, so two libraries that happened to share a path both got the write. Both now also filter on `library_id` (threaded through as `MeasuredMediaFacts.LibraryId` and a new `libraryId` parameter, from `RemuxPassRequest.LibraryId`/`PassThroughDeliverySettings.LibraryId`); a null library id skips the write rather than falling back to the old cross-library match.

## Activity

`Weir.Api/Endpoints/ActivityEndpoints` ports `weir.platform.activity.router`: `recent` (filters, `before_id` paging), `export` (CSV and JSON), `file-history` and its removal, and the `stream` of `activity.latest` frames. The SQL in `Weir.Infrastructure/Activity/ActivityHistoryStore` is the text SQLAlchemy compiles, clause for clause, except for four defects found while porting and fixed here (issue #543; Python keeps all four, so the byte-for-byte comparison in `ActivityHistoryStoreTests` skips the cases that touch them):

1. **`total`/`has_more`.** Python's count query loses its `FROM` when there is no filter (`SELECT count(*)`, which counts one row); `CountAsync` always counts from `activity_events`.
2. **Date filters.** Python compares `date_from`/`date_to` as raw text against the stored column, so a query offset is ignored and a row stored without its `.000000` (an exact second) can sort as earlier than the same instant with one, wrongly excluding it. `Where` normalizes the query value to UTC and compares with `julianday()`, which parses both stored shapes to the same instant.
3. **Paging order.** `ListRecentAsync` orders by `(created_at DESC, id DESC)`, a total order that no longer depends on which plan SQLite picks for a tie (the previous unary-plus hint kept .NET's SQLite 3.53 choosing the same plan as Python's 3.45 for that reason alone). `before_id` pages by that same key — everything strictly after the cursor row — instead of by id alone, so a row tied on `created_at` with the cursor is never skipped or repeated the way Python's id-only paging can.
4. **File-history removal.** Python's `_file_history_filter` (Activity events) also matches a row that never recorded a library id, but `_processing_records` does not, so removing one file's history with a library id could leave its processing records behind. `ProcessingRecordsClause` now gets the same null fallback as `FileHistoryClause`.

Writers never notify listeners directly. `SqliteActivityWriter` records the ids it wrote on the unit of work or raw transaction, and `ActivityNotifications` tells the database's `ActivityLatestNotifier` after the commit (a rollback tells nobody). Code that commits its own raw transaction after `SqliteActivityWriter.Record` calls `ActivityNotifications.TransactionCommitted`, as `RefinerJobStore.InTransactionAsync` does. `RefinerFileLogRetentionTask` prunes processing records hourly by `file_log_retention_days`.

## Publish

Self-contained single-file builds for `win-x64`, `linux-x64` and `linux-arm64`:

```powershell
dotnet publish apps/server/src/Weir.Host -r win-x64 -o apps/server/artifacts/publish/win-x64
dotnet publish apps/server/src/Weir.Host -p:PublishProfile=linux-arm64
```
