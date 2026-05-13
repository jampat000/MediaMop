---
sidebar_position: 2
title: Architecture Decision Records
---

# Architecture Decision Records

ADRs capture locked structural and platform choices for MediaMop. They override ad hoc experimentation when the two conflict.

Some ADR numbers are intentionally absent — those were reserved for drafts or withdrawn decisions.

## Index

| ADR | Title |
|-----|-------|
| [ADR-0001](adr-0001) | Repository and application layout |
| [ADR-0002](adr-0002) | Database and Alembic (SQLite-first) |
| [ADR-0003](adr-0003) | Auth and session model |
| [ADR-0007](adr-0007) | Module-owned worker lanes (SQLite) |
| [ADR-0008](adr-0008) | MediaMopSettings aggregate for runtime configuration |
| [ADR-0009](adr-0009) | Suite-wide timing isolation (durable work) |
| [ADR-0012](adr-0012) | Refiner preflight parity boundary |

## When to add an ADR

Add an ADR when a decision changes module ownership, runtime storage, data safety, security boundaries, release mechanics, or packaging behavior.
