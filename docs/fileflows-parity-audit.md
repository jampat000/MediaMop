# Refiner / FileFlows parity audit

Audit date: 2026-09-01

This is the durable follow-up to closed epic
[#347, Refiner — reach FileFlows and pass it](https://github.com/jampat000/MediaMop/issues/347).
It answers two questions:

1. Did every capability identified by the live FileFlows audit survive later
   Refiner work?
2. Did any closed issue leave a feature present in name but absent from the
   current runtime, UI, API, or tests?

## Scope and method

- Searched all 187 closed MediaMop issues, including issue bodies, for FileFlows,
  parity, intake, file-size, skip/bypass, cleanup, and processed-output work.
- Re-audited epic #347 and every child issue #328–#351 against current source and
  regression tests.
- Re-audited earlier guardrail issues #70 and #92 and post-epic decision issues
  #363, #364, and #366.
- Treated a closed label or historical passing comment as insufficient. Current
  code and current tests are the evidence below.

## Epic capability matrix

| Issue | Capability | Current evidence | Result |
| --- | --- | --- | --- |
| #328 | Dead-code removal | `scripts/check-dead-code.mjs`; no web dead-code allowlist entries | Present |
| #329 | Settings match runtime | `refiner_operator_settings_service.py`, per-library schemas, and settings tests | Present |
| #330 | Migration lint/format | CI runs Ruff check and format over `alembic` | Present |
| #331 | Subber-removal release | Published GitHub release `v2.4.3` | Present |
| #332 | Library-model ADR | `docs/adr/ADR-0014-refiner-libraries-replace-fixed-scopes.md` | Present |
| #333 | Per-library configuration | `refiner_library_model.py`, migration 0011, library API/read-path tests | Present |
| #334 | Explicit file states and Files workbench | `refiner_file_state_service.py`, `refiner-files-section.tsx`, file-state/UI tests | Present |
| #335 | Hold and size settling | `refiner_file_settling.py` and `test_refiner_file_settling.py` | Present |
| #336 | Filesystem watcher plus scan backstop | `refiner_watched_folder_watcher.py` and watcher/periodic-enqueue tests | Present |
| #337 | Schedules and suite pause | schedule/pause services, grid UI, and `test_refiner_schedules_and_pause.py` | Present |
| #338 | Weighted concurrency, caps, priority | runner-unit and job-claim services/tests; move-to-top in Files | Present |
| #339 | Retry, requeue, terminal failure handling | retry/requeue service and API/UI tests | Present |
| #340 | Durable per-file record and retention | file-log model/API/UI and `test_refiner_file_log.py` | Present |
| #341 | Ordered track sorter | rule-set workspace and `test_refiner_track_sorters.py` | Present |
| #342 | Metadata, artwork, attachment cleanup | metadata rule service/UI and `test_refiner_metadata_rules.py` | Present |
| #343 | Original-language selection | encrypted metadata-provider settings and original-language tests | Present |
| #344 | Sidecars travel before source cleanup | sidecar migration service and failure-blocks-deletion tests | Present |
| #345 | Hardware acceleration controls | hardware detection/decision service, UI, and hardware tests | Present |
| #346 | Complete v1 API/OpenAPI surface | `test_refiner_api_surface.py` and generated OpenAPI/types | Present |
| #348 | Full supported-container allowlist | media allowlist and `test_refiner_media_allowlist.py` | Present |
| #349 | Output collision policy | per-library policy, activity record, and collision tests | Present |
| #350 | Manager-neutral integration | media-manager port/dialects and manager-neutral Refiner tests | Present |
| #351 | Manager library discovery and drift | discovery API/UI, path translation, and discovery tests | Present |

## Additional features found outside the epic

### File-size intake and rejected-file cleanup (#92)

MediaMop already has both levels FileFlows operators expect:

- a global conservative minimum input size and target-volume free-space guardrail
  under Refiner processing settings;
- per-library minimum and maximum sizes, include/exclude path rules, downloader
  folder markers, and created/modified windows;
- a per-library **When a file is rejected** choice: leave it in place or delete
  only the rejected file after readiness checks. A populated parent folder is not
  removed by this rejection path.

The bypass action intentionally ignores the minimum-size rule because it is an
explicit operator exception, but it still enforces stability, no-writer,
fingerprint, output validation, sidecar, and source-cleanup safety.

### Intentional edge-case bypass

The Files workbench now provides **Pass through unchanged**. It preserves every
stream, bypasses Refiner selection/metadata rules, places a validated unchanged
output in the library's processed-output tree, and then performs normal successful
source cleanup. Pending ordinary work for the same file is converted in place so
the explicit choice cannot race a duplicate job.

### Large unchanged files (#70)

The audit found a real regression: the hardlink primitive still existed and had a
unit test, but Refiner no longer called it, so every unchanged file performed a full
copy. The current implementation reconnects that fast path only on Windows, where
the held source handle mandatorily denies writers for the complete pass. It creates
a staged same-volume hardlink, validates it, then atomically publishes it. A
cross-volume link falls back to the progress-reporting validated copy.

If a later cleanup safety gate preserves the watched source, MediaMop immediately
replaces the output link with an independent validated copy. That uncommon fallback
prevents a future writer at the watched path from mutating the published output.

Linux and Docker deliberately keep the independent copy path because `flock` is
advisory; an existing downloader descriptor could otherwise mutate the output
through a shared inode after the watched name is removed.

## Closed decision issues

- **#363:** migration 0025 drops the two singleton tables. Scope-shaped compatibility
  APIs remain but read/write libraries, so there is one configuration store.
- **#364:** Deluno#331 confirmed `id`, `mediaType`, `rootPath`, `importWorkflow`, and
  `processorOutputPath` from a populated live manifest. MediaMop now parses those
  exact keys, seeds refine-before-import output paths, and tests the captured body.
- **#366:** update mode, startup/interval controls, tray double-click, Docker version
  behavior, and the docs-site dependency remediation were re-landed on `main` in
  later changes. GitHub contains no surviving feature branch or open PR for them.

## Conclusion

No unimplemented FileFlows-audit feature remains hidden behind a closed issue. The
one runtime regression found by this audit—the disconnected same-volume unchanged
fast path—was remediated and covered by validation-before-publication tests. Future
parity claims must update this document when they change the matrix or its safety
rationale.
