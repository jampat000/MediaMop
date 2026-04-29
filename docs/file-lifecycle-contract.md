# File lifecycle contract

MediaMop must never report a partial media mutation as successful.

## Required mutation pattern

- Write or copy into a staged file first.
- Validate the staged file before final placement where validation is available.
- Replace the final path atomically with `os.replace` when the filesystem supports it.
- For cross-filesystem moves, copy into a hidden partial file in the destination directory, then atomically replace the final path.
- Only update job/activity success after the final file exists and passes the relevant safety checks.
- Do not delete watched-folder or output-folder material unless the operation has traceable intent and an output safety check has passed.

Backend code should use `mediamop.platform.file_lifecycle.mutations` for final media file placement instead of direct `shutil.move`, direct final-path copies, or unlink-then-copy patterns.

## Deletion rules

- Missing files are already absent, not success with hidden work.
- Locked/in-use files must produce an operator-readable skipped or failed reason.
- Pruner destructive actions must use stored preview snapshots, never a fresh live query.
