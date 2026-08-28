# ADR-0014: Refiner asks a port, and "no answer" is not "nothing"

## Status

Accepted — applies to every outbound question MediaMop asks a media manager, and to
every gate that acts on the answer.

## Context

[ADR-0013](ADR-0013-media-managers-are-kinds-not-products.md) made a connection a row
with a `kind`, and made the **inbound** direction a dialect: a manager posts an event,
the dialect unwraps it, everything downstream reads one neutral shape.

The outbound direction never followed. Refiner resolved a single `(url, key)` pair from
a hardcoded `{"movie": "radarr", "tv": "sonarr"}` map, and four cleanup modules skipped
even that and built their own HTTP. Three things followed from that, and the third is
the reason this ADR exists:

1. **A library could only ever be served by one manager.** Two Radarr instances — an
   ordinary 4K-plus-1080p setup — could not both be consulted, and neither could a
   manager running alongside another during a migration.
2. **Product names crossed into module code.** Fourteen files under `modules/refiner/`
   named Radarr or Sonarr, including the reasons shown to operators.
3. **A manager with nothing to say looked exactly like a quiet one.** Every path
   returned a list of queue rows. An empty list meant "nothing is importing" — and it
   also meant "this manager cannot tell us", "this manager is down", and "no manager is
   configured". A Deluno-managed library therefore got *no* upstream safety check while
   reporting a clean pass: `should_block_for_upstream` could never fire, because the
   only queue dialect was arr-v3.

The third one is a data-safety bug wearing the costume of a missing feature. Refiner
deletes folders on the strength of these answers.

## Decision

### 1. Three questions, one port, one dialect per kind

`platform/media_managers/manager_port.py` defines what may be asked:

- `describe()` — which scopes and roots this manager covers, and which of the questions
  below it can answer at all.
- `queue_rows()` — what is mid-import, in a shape the media-scope dialects already read.
- `library_truth()` — which library files this manager still keeps, which is the gate in
  front of a delete.

`manager_dialects.py` implements one port per kind, mirroring `import_events.py` on the
inbound side. Adding a manager is a port, not a route, a job kind, a module, or a column.

### 2. Every answer is three-valued

`reported` / `no_signal` / `unreachable`. **Only `reported` carries data, and only
`reported` with nothing in it means "safe to proceed".**

This is the whole point. An empty tuple collapsed three different facts into one, and
the one it chose was the permissive one. Naming the other two forces every caller to
decide what to do about them, in code that a reader can check.

### 3. A scope resolves to N connections, and any one of them can block

`connections_for_scope` returns every enabled, credentialed manager that looks after a
media scope. Refiner asks all of them and blocks the file if **any** reports an
in-progress import. Scope coverage is a static property of the kind, so binding costs no
requests; `describe()` is for the settings surface, not the scan loop.

### 4. What to do about silence is the caller's decision, not the port's

The right answer genuinely differs, so the port does not pick one:

- **Watched-folder scan** (non-destructive): degrade to the file-settling gates, and
  report which manager could not be reached. Refusing to process anything because a
  manager is down would stop the app doing its job over a safety check that is advisory.
- **Anything in front of a delete** (output cleanup, season cleanup, failure sweep):
  refuse. An import check MediaMop could not make is not an import check that passed.

### 5. Blocked-upstream reasons name the connection

"Deluno (Main) is still importing this file", never "Sonarr says wait". The operator
configured a connection with a name; that is the thing they recognise, and it is the
only thing that stays true when a library is served by two of the same product.

Attribution is carried alongside the domain row rather than inside it: `domain.py` was
already vendor-neutral and does not change.

### 6. A documented rate limit is respected, not retried through

Deluno publishes 3000 requests per 60s per key and answers a breach with `429` plus
`Retry-After`. That is surfaced as a distinct error type and reported as a degraded
answer. Retrying inside the call would spend the rest of the window on the retry.

## Consequences

- A Deluno-managed library gets a real upstream safety check for the first time.
- A manager that cannot report library truth cannot clear a folder for deletion. For a
  Deluno-only instance that means output-folder cleanup stays off — which is what
  already happened when no Radarr was configured, now said out loud in the activity
  detail rather than left to be inferred.
- A queue state MediaMop does not recognise is treated as **still in progress**. A
  wrong "wait" costs one scan cycle; a wrong "proceed" costs a file.
- `refiner.candidate_gate.v1` gained a fourth verdict, `no_upstream_signal`, and its
  manual-enqueue payload asks for a `media_scope` rather than a product `target`. This
  is a breaking change to a diagnostic lane with no UI, taken deliberately rather than
  keeping a vendor name in the v1 contract.
- `GET /api/v1/media-managers/capabilities` exposes what each connection can be asked,
  so "this manager will not give you an upstream check" is visible before it matters.
- `platform/arr_library/` is now only the frozen-KDF credential crypto plus the legacy
  settings row that migration `0009` copied out of but did not drop. Removing the rest
  needs a migration and is not this change.

## Out of scope

- Dropping `arr_library_operator_settings`. That is a schema change.
- The node-graph/flow engine — explicitly out of scope for the epic this belongs to.
- Refiner preflight probe depth, which [ADR-0012](ADR-0012-refiner-preflight-parity-boundary.md) bounds.

## Related

- ADR-0013 — a media manager is a kind, not a product name (the inbound half)
- ADR-0012 — Refiner preflight parity boundary
- `docs/operator-messaging-standard.md` — the wording rules the reasons follow
