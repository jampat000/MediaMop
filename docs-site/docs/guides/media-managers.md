---
sidebar_position: 5
title: Connecting Deluno, Sonarr and Radarr
---

# Connecting Deluno, Sonarr and Radarr

Under **Settings → Media managers**, Weir can connect to the tools that manage your downloads and
library, so cleaning happens automatically instead of you moving files around by hand.

There are four kinds of connection: **Deluno**, **Sonarr**, **Radarr**, and **Something else** for
anything that can send Weir a message directly.

## Deluno: automatic hand-off

Deluno hands a file to Weir to work on, and waits to be told it's ready. This is the fully
automatic setup: Deluno tells Weir about a new file, Weir cleans it, and Deluno is told when the
cleaned copy is ready to import. You don't move anything by hand.

The Weir library still needs a watched folder: Weir only accepts a hand-off for a file inside one.
Point it at the folder Deluno downloads into, using the same path Deluno sees.

## Sonarr and Radarr: checking before Weir touches a file

Connecting Sonarr or Radarr lets Weir check what they're still importing before it acts on a file.
This matters because your download client and Sonarr/Radarr are often still working with a file at
the same time Weir notices it in the watched folder — Weir checking their queue first avoids
racing an import that's already in progress.

The same connection also powers **Download again**: if you change your rules later and an already
imported file lost a track you now want to keep, Weir can ask Radarr or Sonarr to fetch that
release again.

- Connecting **Radarr** lets Weir check what Radarr is still importing, and download a film again.
- Connecting **Sonarr** lets Weir check what Sonarr is still importing, and download an episode
  again.

## Sonarr and Radarr: getting cleaned files imported

Sonarr and Radarr don't hand files to Weir. Instead, your download client finishes into Weir's
**watched folder**, Weir writes the cleaned copy to its **output folder**, and a **remote path
mapping** in Sonarr/Radarr points them at the output folder. They only ever see cleaned files.

### 1. Set up the library in Weir

Open **Processing → Libraries** and edit the library:

- **Watched folder**: where your download client finishes files, e.g. `/media/downloads/complete/tv`.
- **Output folder**: where Weir puts cleaned files, e.g. `/media/weir/tv`.
- **After cleaning, remove the original download**: turn this **off** if you use torrents. The torrent
  needs its files to keep seeding, and if they disappear, Sonarr stops treating the download as
  finished and never imports it. Your download client or Sonarr removes the original later, under
  your normal seeding rules. Weir remembers what it has already cleaned, so it won't clean the same
  file twice.
- **Existing output**: leave it on anything except **Keep both**. Keep both renames the cleaned file,
  and Sonarr only looks for the original name.

### 2. Connect Sonarr (or Radarr) to Weir

Under **Settings → Media managers**, add Sonarr with its address and API key. You'll find the key in
Sonarr under **Settings → General**.

### 3. Add the remote path mapping in Sonarr

The library's **Media manager** section in Weir shows the exact values, with copy buttons. In Sonarr, go
to **Settings → Download Clients → Remote Path Mappings** and press **+**:

| Field | Value |
| --- | --- |
| Host | Exactly what's in your download client's **Host** field on that same screen, e.g. `qbittorrent` |
| Remote Path | Weir's watched folder, e.g. `/media/downloads/complete/tv/` |
| Local Path | Weir's output folder, e.g. `/media/weir/tv/` |

- The output folder must already exist, or Sonarr won't save the mapping.
- Add one mapping for each download client Host.
- Keep **Completed Download Handling** switched on. This setup relies on it.
- If Sonarr, Weir and your download client see the folders at different paths, use the path **each app
  itself** sees. Giving every container the same folders at the same paths avoids that.

### 4. Check it

In Weir, press **Check again** in the library's **Media manager** section. Weir reads Sonarr's remote path
mappings, download clients and queue — it never changes Sonarr's settings — and shows ✓, or a plain
explanation of what to fix.

### What you'll see

When a download finishes, Sonarr shows **"No files found are eligible for import"** until Weir is done.
That's expected: Sonarr checks again every minute, with no time limit, and imports the cleaned file as
soon as it appears. Weir only ever publishes a finished file, so Sonarr can't import one halfway through.

If Weir can't clean a file, what Sonarr sees depends on the library's **When retries run out** setting:

- **Hand the original back unchanged** (the default): Sonarr imports the original, uncleaned.
- **Keep it until someone acts**: Sonarr waits, and Weir shows the file on hold.
- **Reject the release so a different one is found**: Weir removes the download and blocklists it in Sonarr, so it searches again.

Files below the library's minimum size are never cleaned, so Sonarr waits on them indefinitely. Keep
the minimum size below your smallest real episode.

## Anything else

A tool that isn't Deluno, Sonarr or Radarr can still hand files to Weir directly, by posting to its
webhook endpoint (`/api/v1/intake/webhook/native` for a connection of kind **Something else**).
See the [API reference](../api) for the full request shape.
