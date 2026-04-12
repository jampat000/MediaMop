"""Subber module — durable ``subber_jobs`` queue and in-process workers (ADR-0007).

Production durable kinds use the ``subber.*`` prefix on ``subber_jobs`` only. Operator timing for
scheduled Subber families must stay family-local per ADR-0009 (this pass: manual enqueue only for
``subber.supplied_cue_timeline.constraints_check.v1`` — no shared periodic state with other modules).
"""
