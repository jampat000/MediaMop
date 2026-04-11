# ADR-0004: Reserved number (no document)

## Status

**Reserved.** This number is intentionally unused so ADR filenames stay stable and greppable.

## Context

ADR numbers were assigned out of strict chronological order while the worker-lane and Fetcher split landed. **0004** is held open rather than renumbering accepted ADRs.

## Decision

No architectural content is attached to **ADR-0004**. Future ADRs should prefer the next free number after the highest published ADR unless a reserved slot is explicitly repurposed.

## Consequences

Discoverability lives in [`README.md`](README.md), which lists every published ADR and notes reserved slots.
