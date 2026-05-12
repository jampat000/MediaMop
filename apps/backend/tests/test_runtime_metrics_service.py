from __future__ import annotations

from mediamop.platform.metrics.service import (
    build_runtime_metrics_summary,
    record_http_request,
    record_log_record,
    record_module_job_event,
    record_module_savings,
    render_prometheus_metrics,
    reset_runtime_metrics_for_tests,
    set_module_queue_depth,
)


def test_runtime_metrics_summary_and_prometheus_include_module_job_metrics() -> None:
    reset_runtime_metrics_for_tests()

    record_http_request(method="GET", route="/api/v1/health", status_code=200, duration_ms=12.5)
    record_http_request(method="POST", route="/api/v1/refiner/jobs", status_code=500, duration_ms=33.0)
    record_log_record("error")
    record_module_job_event(module="refiner", event="started")
    record_module_job_event(module="refiner", event="completed")
    record_module_job_event(module="subber", event="failed")
    set_module_queue_depth(module="refiner", depth=3)
    set_module_queue_depth(module="subber", depth=1)

    output = render_prometheus_metrics()

    assert 'mediamop_module_jobs_total{module="refiner",event="started"} 1' in output
    assert 'mediamop_module_jobs_total{module="refiner",event="completed"} 1' in output
    assert 'mediamop_module_jobs_total{module="subber",event="failed"} 1' in output
    assert 'mediamop_module_queue_depth{module="refiner"} 3' in output
    assert 'mediamop_module_queue_depth{module="subber"} 1' in output
    assert "mediamop_http_requests_total 2" in output


def test_record_module_savings_increments_correctly() -> None:
    reset_runtime_metrics_for_tests()

    record_module_savings(module="refiner", bytes_saved=1_000_000)
    record_module_savings(module="refiner", bytes_saved=500_000)
    record_module_savings(module="pruner", bytes_saved=2_000_000)

    summary = build_runtime_metrics_summary()
    assert summary["module_savings_bytes"]["refiner"] == 1_500_000
    assert summary["module_savings_bytes"]["pruner"] == 2_000_000


def test_record_module_savings_ignores_nonpositive() -> None:
    reset_runtime_metrics_for_tests()

    record_module_savings(module="refiner", bytes_saved=0)
    record_module_savings(module="refiner", bytes_saved=-100)

    summary = build_runtime_metrics_summary()
    assert "refiner" not in summary["module_savings_bytes"]


def test_summary_includes_module_savings_bytes() -> None:
    reset_runtime_metrics_for_tests()

    record_module_savings(module="refiner", bytes_saved=12_345_678)

    summary = build_runtime_metrics_summary()
    assert "module_savings_bytes" in summary
    assert summary["module_savings_bytes"] == {"refiner": 12_345_678}


def test_render_prometheus_includes_savings_metric() -> None:
    reset_runtime_metrics_for_tests()

    record_module_savings(module="refiner", bytes_saved=12_345_678)
    record_module_savings(module="pruner", bytes_saved=9_876_543)

    output = render_prometheus_metrics()

    assert "# HELP mediamop_module_savings_bytes_total" in output
    assert "# TYPE mediamop_module_savings_bytes_total counter" in output
    assert 'mediamop_module_savings_bytes_total{module="refiner"} 12345678' in output
    assert 'mediamop_module_savings_bytes_total{module="pruner"} 9876543' in output


def test_render_prometheus_omits_savings_section_when_empty() -> None:
    reset_runtime_metrics_for_tests()

    output = render_prometheus_metrics()

    assert "mediamop_module_savings_bytes_total" not in output
