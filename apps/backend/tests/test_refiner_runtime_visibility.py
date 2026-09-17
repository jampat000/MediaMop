"""Unit tests for Refiner runtime settings DTO (env-backed worker count semantics)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from weir.core.config import WeirSettings
from weir.refiner.refiner_runtime_visibility import refiner_runtime_settings_from_settings


def test_refiner_runtime_settings_default_workers_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WEIR_REFINER_WORKER_COUNT", raising=False)
    s = WeirSettings.load()
    out = refiner_runtime_settings_from_settings(s)
    assert out.in_process_refiner_worker_count == 8
    assert out.in_process_workers_disabled is False
    assert out.in_process_workers_enabled is True
    assert "8" in out.worker_mode_summary
    assert "processing settings" in out.worker_mode_summary.lower()


def test_refiner_runtime_settings_multi_worker_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEIR_REFINER_WORKER_COUNT", "3")
    s = WeirSettings.load()
    assert s.refiner_worker_count == 3
    out = refiner_runtime_settings_from_settings(s)
    assert out.in_process_refiner_worker_count == 3
    assert out.in_process_workers_enabled is True
    assert "3" in out.worker_mode_summary
    assert "sqlite" in out.sqlite_throughput_note.lower()


def test_refiner_runtime_settings_one_worker_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEIR_REFINER_WORKER_COUNT", "1")
    s = WeirSettings.load()
    out = refiner_runtime_settings_from_settings(s)
    assert out.in_process_refiner_worker_count == 1
    assert "one" in out.worker_mode_summary.lower()


def test_refiner_runtime_settings_includes_lane_isolation_in_multi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEIR_REFINER_WORKER_COUNT", "2")
    s = WeirSettings.load()
    out = refiner_runtime_settings_from_settings(s)
    assert "refiner_jobs" in out.worker_mode_summary.lower()


def test_refiner_runtime_settings_clamp_high_via_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEIR_REFINER_WORKER_COUNT", "99")
    s = WeirSettings.load()
    assert s.refiner_worker_count == 8
    out = refiner_runtime_settings_from_settings(s)
    assert out.in_process_refiner_worker_count == 8


def test_refiner_runtime_settings_replace_without_full_reload() -> None:
    base = WeirSettings.load()
    s = replace(base, refiner_worker_count=4)
    out = refiner_runtime_settings_from_settings(s)
    assert out.in_process_refiner_worker_count == 4
    assert "4" in out.worker_mode_summary
