# ADR-0012: Refiner remux preflight parity boundary (FileFlows-aligned, bounded)

## Status

**Accepted**.

## Context

Refiner `refiner.file.remux_pass.v1` needs stronger preflight behavior to align with the practical intent of FileFlows "Video File" analysis, while keeping MediaMop's existing cleanup contracts unchanged.

Without an explicit boundary, parity work risks either:

- under-specifying probe depth (weak stream truth), or
- over-extending into extra post-processing complexity and technical debt.

## Decision

1. **Preflight parity scope is probe-depth + observability only**
   - Refiner preflight now supports bounded ffprobe controls:
     - `MEDIAMOP_REFINER_PROBE_SIZE_MB` (default `10`, clamp `1..1024`)
     - `MEDIAMOP_REFINER_ANALYZE_DURATION_SECONDS` (default `10`, clamp `1..300`)
   - These settings are loaded at API startup via `MediaMopSettings`.
   - Remux pass results include stable preflight fields:
     - `preflight_status`
     - `preflight_reason`
     - `preflight_probe_settings` (when probe/planning completes)

2. **Parity boundary excludes cleanup behavior changes**
   - Pass 1/1b/2/3a/3b/4 cleanup gates and delete contracts remain authoritative and unchanged.
   - Preflight failure (`failed_before_execution`) remains non-destructive and must not emit success-only cleanup mutation fields.

3. **No new module-level settings registry**
   - Probe controls remain in `MediaMopSettings` per ADR-0008.
   - Timing/schedule independence across families remains governed by ADR-0009.

## Related

- [ADR-0008](ADR-0008-mediamop-settings-aggregate-runtime-config.md)
- [ADR-0009](ADR-0009-suite-wide-timing-isolation.md)
- [ADR-0007](ADR-0007-module-owned-worker-lanes.md)

## Consequences

- Operators can tune probe depth for difficult media while keeping bounded resource behavior.
- Activity/result payloads gain clearer preflight truth for diagnosis.
- Existing post-work cleanup logic stays stable, reducing regression risk during parity work.

## Compliance

- Any future parity expansion beyond preflight depth/observability requires a follow-up ADR update.
- Tests must continue to enforce:
  - bounded probe argv behavior,
  - preflight failure contract (`failed_before_execution` non-destructive),
  - unchanged cleanup regression coverage.

