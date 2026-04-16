"""Pruner module — durable ``pruner_jobs`` queue and in-process workers (ADR-0007).

Phase 1 establishes the lane only (table, ``pruner.*`` job_kind prefix, workers). No removal
job families are shipped yet. See ``docs/pruner-forward-design-constraints.md`` for locked
forward design (TV/Movies and per server-instance independence; Emby + Jellyfin + Plex scope).
"""
