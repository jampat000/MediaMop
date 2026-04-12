"""Trimmer module — durable ``trimmer_jobs`` queue and in-process workers (ADR-0007).

Production durable kinds use the ``trimmer.*`` prefix on ``trimmer_jobs`` only. Operator timing for
scheduled Trimmer families must stay family-local per ADR-0009 (shipped families here: manual enqueue
only — ``trimmer.trim_plan.constraints_check.v1``, ``trimmer.supplied_trim_plan.json_file_write.v1``;
no shared periodic state with other modules).
"""
