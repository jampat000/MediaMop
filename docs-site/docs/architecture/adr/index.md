---
sidebar_position: 2
title: Architecture Decision Records
---

# Architecture Decision Records

ADRs capture locked structural and platform choices for Weir. They override ad hoc experimentation when the two conflict.

Some ADR numbers are intentionally absent — those were reserved for drafts or withdrawn decisions.

## Index

| ADR | Title |
|-----|-------|
| [ADR-0001](adr-0001) | Repository and application layout |
| [ADR-0002](adr-0002) | Database and Alembic (SQLite-first) |
| [ADR-0003](adr-0003) | Auth and session model |
| [ADR-0007](adr-0007) | Module-owned worker lanes (SQLite) |
| [ADR-0008](adr-0008) | WeirSettings aggregate for runtime configuration |
| [ADR-0009](adr-0009) | Suite-wide timing isolation (durable work) |
| [ADR-0012](adr-0012) | Refiner preflight parity boundary |
| [ADR-0017](https://github.com/jampat000/Weir/blob/main/docs/adr/ADR-0017-backend-on-dotnet.md) | Weir's backend moves to C# on .NET 10 |

ADR-0001 and ADR-0002 describe the original Python backend. ADR-0017 replaced it with the .NET server in `apps/server`; each of those pages notes what changed.

## When to add an ADR

Add an ADR when a decision changes module ownership, runtime storage, data safety, security boundaries, release mechanics, or packaging behavior.
