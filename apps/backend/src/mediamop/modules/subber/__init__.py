"""Subber module — durable ``subber_jobs`` queue and in-process workers (ADR-0007).

Production durable kinds use the ``subber.*`` prefix on ``subber_jobs`` only. TV and Movies schedules
and state are independent; periodic library scans read ``subber_settings`` only (ADR-0009).
"""
