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

{/* STEPS PENDING: filled in by the remote-path-mapping work */}

The exact steps for pointing Sonarr and Radarr at Weir's cleaned output are being finalized in a
separate piece of work and will be added here once that's done.

## Anything else

A tool that isn't Deluno, Sonarr or Radarr can still hand files to Weir directly, by posting to its
webhook endpoint (`/api/v1/intake/webhook/native` for a connection of kind **Something else**).
See the [API reference](../api) for the full request shape.
