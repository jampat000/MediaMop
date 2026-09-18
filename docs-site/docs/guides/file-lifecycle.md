---
sidebar_position: 3
title: How Weir Keeps Your Files Safe
---

# How Weir keeps your files safe

Weir never touches your original file directly, and it never reports a file as done until the
cleaned copy has actually been checked. This page explains what that means in practice.

## Weir works on a copy, not your original

When Weir cleans a file, it writes the new copy — with the tracks you didn't ask for stripped out
— into a **work folder**, not straight into your output folder. Your original file in the watched
folder is only ever read, never modified, while this happens.

- If your library doesn't set its own work folder, Weir uses a default one under its own data
  folder, separate for movies and TV.
- Before it starts writing, Weir checks there's enough free disk space at both the work folder and
  the output folder. If there isn't, it skips the file and tells you why, rather than starting a
  write it can't finish.

## Nothing "half-written" ever appears in your output folder

Once the new copy is ready in the work folder, Weir doesn't just drop it into place. Getting the
finished file to your output folder is a two-step move:

1. **Publish under a hidden name first.** Weir copies (or, when it can, hard-links) the file into
   the output folder under a hidden temporary name — the same folder, but not the name you'll
   actually see.
2. **Swap it into place in one step.** Only once that hidden copy exists completely does Weir
   rename it to its real name. On the same drive, that rename is atomic: from the outside, the
   file either doesn't exist yet, or exists complete — there's no moment where a program watching
   that folder could see a partial file under its final name.

If anything goes wrong partway — the disk fills up, the process is interrupted, the source turns
out to have changed underneath it — Weir cleans up the hidden temporary file and leaves your
output folder exactly as it was. Nothing partial is ever left at the final path.

When the work folder and the output folder are on different drives (so a rename can't cross
between them), Weir copies into the hidden temporary file on the *destination* drive first, and
still only exposes it under its real name once that copy is complete.

## Weir hands your file back if it can't clean it

If Weir can't produce a usable result — the release turns out to have no tracks worth keeping, for
example — it doesn't leave a broken file behind or silently drop your download. It hands the
original file back unchanged and tells you why in Activity, so you (or your media manager) can
decide what to do next.

## Subtitles and other extra files travel too, safely

If your rules keep sidecar files — subtitles, `.nfo` files, cover art — next to the video, Weir
copies them across to the output folder using the same safe-write process, renamed to match the
cleaned file. They're **copied, not moved**: if a subtitle can't be copied for some reason, Weir
leaves your original folder in place rather than deleting something it couldn't safely bring
across. If a file with the same name already exists in the output folder, Weir leaves it alone
rather than overwriting something you may have already edited.

## Deleting the original

Weir only deletes the original file (or the source folder it came from) after the cleaned copy
exists at its final path and any sidecars that needed to travel have been copied successfully. A
file that's missing is treated as already gone, not as a completed deletion with something hidden
behind it — and a file that's locked or in use produces a message you can read in Activity, not a
silent skip.

## Library mode: cleaning files you already have

Cleaning a file that's already in your library, in place, follows the same rule: Weir builds the
cleaned version alongside the original first and only swaps it in once the new copy is confirmed
good. It never leaves your library with a file half-replaced.
