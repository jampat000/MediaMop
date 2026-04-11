"""Subber module boundary — reserved for future implementation.

Durable work for this module must use its own queue and workers (module-owned lane), not
``fetcher_jobs`` or ``refiner_jobs``. See ``docs/adr/ADR-0007-module-owned-worker-lanes.md``.
Operator timing contracts for ``subber.*`` jobs must follow
``docs/adr/ADR-0009-suite-wide-timing-isolation.md``.
"""
