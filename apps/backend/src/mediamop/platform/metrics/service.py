"""In-memory runtime metrics used by the dashboard and Prometheus scrape endpoint."""

from __future__ import annotations

import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import TypedDict


@dataclass
class RouteMetric:
    count: int = 0
    total_duration_ms: float = 0.0


class RouteSummary(TypedDict):
    route: str
    request_count: int
    average_response_ms: float


class RuntimeMetricsSummary(TypedDict):
    uptime_seconds: float
    total_requests: int
    average_response_ms: float
    error_log_count: int
    status_counts: dict[str, int]
    busiest_routes: list[RouteSummary]
    module_job_counts: dict[str, dict[str, int]]
    module_queue_depths: dict[str, int]
    module_savings_bytes: dict[str, int]


class RuntimeMetricsStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.started_at = time.time()
        self.http_total = 0
        self.http_total_duration_ms = 0.0
        self.status_counts: Counter[str] = Counter()
        self.route_metrics: dict[str, RouteMetric] = defaultdict(RouteMetric)
        self.log_counts: Counter[str] = Counter()
        self.module_job_counts: Counter[tuple[str, str]] = Counter()
        self.module_queue_depths: dict[str, int] = defaultdict(int)
        self.module_savings_bytes: Counter[str] = Counter()

    def record_request(self, *, method: str, route: str, status_code: int, duration_ms: float) -> None:
        bucket = f"{status_code // 100}xx"
        label = f"{method.upper()} {route}"
        with self._lock:
            self.http_total += 1
            self.http_total_duration_ms += max(duration_ms, 0.0)
            self.status_counts[bucket] += 1
            metric = self.route_metrics[label]
            metric.count += 1
            metric.total_duration_ms += max(duration_ms, 0.0)

    def record_log(self, level: str) -> None:
        with self._lock:
            self.log_counts[level.upper()] += 1

    def record_module_job_event(self, *, module: str, event: str) -> None:
        if not module:
            return
        if event not in {"started", "completed", "failed"}:
            return
        with self._lock:
            self.module_job_counts[(module, event)] += 1

    def set_module_queue_depth(self, *, module: str, depth: int) -> None:
        if not module:
            return
        with self._lock:
            self.module_queue_depths[module] = max(0, int(depth))

    def record_module_savings(self, *, module: str, bytes_saved: int) -> None:
        if not module:
            return
        if bytes_saved <= 0:
            return
        with self._lock:
            self.module_savings_bytes[module] += int(bytes_saved)

    def summary(self) -> RuntimeMetricsSummary:
        with self._lock:
            uptime_seconds = max(time.time() - self.started_at, 0.0)
            average_response_ms = self.http_total_duration_ms / self.http_total if self.http_total else 0.0
            busiest = sorted(
                self.route_metrics.items(),
                key=lambda item: (-item[1].count, item[0]),
            )[:5]
            module_job_counts: dict[str, dict[str, int]] = {}
            for (module, event), count in sorted(self.module_job_counts.items()):
                bucket = module_job_counts.setdefault(module, {"started": 0, "completed": 0, "failed": 0})
                bucket[event] = int(count)
            return {
                "uptime_seconds": uptime_seconds,
                "total_requests": self.http_total,
                "average_response_ms": average_response_ms,
                "error_log_count": self.log_counts["ERROR"] + self.log_counts["CRITICAL"],
                "status_counts": {
                    "2xx": self.status_counts["2xx"],
                    "3xx": self.status_counts["3xx"],
                    "4xx": self.status_counts["4xx"],
                    "5xx": self.status_counts["5xx"],
                },
                "busiest_routes": [
                    {
                        "route": route,
                        "request_count": metric.count,
                        "average_response_ms": metric.total_duration_ms / metric.count if metric.count else 0.0,
                    }
                    for route, metric in busiest
                ],
                "module_job_counts": module_job_counts,
                "module_queue_depths": dict(self.module_queue_depths),
                "module_savings_bytes": {m: int(v) for m, v in self.module_savings_bytes.items()},
            }

    def render_prometheus(self) -> str:
        summary = self.summary()
        status_counts = summary["status_counts"]
        lines = [
            "# HELP mediamop_process_uptime_seconds Seconds since the current MediaMop process started.",
            "# TYPE mediamop_process_uptime_seconds gauge",
            f"mediamop_process_uptime_seconds {summary['uptime_seconds']:.3f}",
            "# HELP mediamop_http_requests_total Total HTTP requests handled by MediaMop.",
            "# TYPE mediamop_http_requests_total counter",
            f"mediamop_http_requests_total {summary['total_requests']}",
            "# HELP mediamop_http_average_response_ms Average HTTP response time in milliseconds.",
            "# TYPE mediamop_http_average_response_ms gauge",
            f"mediamop_http_average_response_ms {summary['average_response_ms']:.3f}",
            "# HELP mediamop_log_records_total Total log records by level.",
            "# TYPE mediamop_log_records_total counter",
        ]
        for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            lines.append(f'mediamop_log_records_total{{level="{level.lower()}"}} {self.log_counts[level]}')
        for bucket, count in status_counts.items():
            lines.append(f'mediamop_http_status_total{{status="{bucket}"}} {count}')
        for module, counts in summary["module_job_counts"].items():
            for event, count in counts.items():
                lines.append(f'mediamop_module_jobs_total{{module="{module}",event="{event}"}} {count}')
        for module, depth in summary["module_queue_depths"].items():
            lines.append(f'mediamop_module_queue_depth{{module="{module}"}} {depth}')
        savings = summary["module_savings_bytes"]
        if savings:
            lines.append(
                "# HELP mediamop_module_savings_bytes_total Bytes saved by each module (Refiner remux, Pruner removal)."
            )
            lines.append("# TYPE mediamop_module_savings_bytes_total counter")
            for module, total in sorted(savings.items()):
                lines.append(f'mediamop_module_savings_bytes_total{{module="{module}"}} {total}')
        return "\n".join(lines) + "\n"


runtime_metrics = RuntimeMetricsStore()


def record_http_request(*, method: str, route: str, status_code: int, duration_ms: float) -> None:
    runtime_metrics.record_request(method=method, route=route, status_code=status_code, duration_ms=duration_ms)


def record_log_record(level: str) -> None:
    runtime_metrics.record_log(level)


def record_module_job_event(*, module: str, event: str) -> None:
    runtime_metrics.record_module_job_event(module=module, event=event)


def set_module_queue_depth(*, module: str, depth: int) -> None:
    runtime_metrics.set_module_queue_depth(module=module, depth=depth)


def record_module_savings(*, module: str, bytes_saved: int) -> None:
    runtime_metrics.record_module_savings(module=module, bytes_saved=bytes_saved)


def build_runtime_metrics_summary() -> RuntimeMetricsSummary:
    return runtime_metrics.summary()


def render_prometheus_metrics() -> str:
    return runtime_metrics.render_prometheus()


def reset_runtime_metrics_for_tests() -> None:
    global runtime_metrics
    runtime_metrics = RuntimeMetricsStore()
