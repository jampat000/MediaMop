from __future__ import annotations

from mediamop.platform.metrics.service import (
    record_http_request,
    record_log_record,
    record_module_job_event,
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
