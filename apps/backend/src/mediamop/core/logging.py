"""Process-wide logging configuration."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from traceback import format_exception

from mediamop.core.config import MediaMopSettings
from mediamop.platform.http.request_context import current_job_id, current_request_id
from mediamop.platform.metrics.service import record_log_record


class MediaMopLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = current_request_id()
        record.job_id = current_job_id()
        if not getattr(record, "_mediamop_metrics_counted", False):
            record_log_record(record.levelname)
            record._mediamop_metrics_counted = True
        return True


class JsonLineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "source": f"{Path(record.pathname).name}:{record.lineno}",
            "detail": getattr(record, "detail", None),
            "correlation_id": getattr(record, "correlation_id", None),
            "job_id": getattr(record, "job_id", None),
        }
        if record.exc_info:
            payload["traceback"] = "".join(format_exception(*record.exc_info)).strip()
        return json.dumps(payload, ensure_ascii=True)


def configure_logging(settings: MediaMopSettings) -> None:
    """Idempotent-friendly logging for API, workers, and persisted runtime event logs."""

    level_name = settings.log_level.upper()
    level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    shared_filter = MediaMopLogFilter()

    console = logging.StreamHandler()
    console.setLevel(level)
    console.addFilter(shared_filter)
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(console)

    log_path = Path(settings.log_dir) / "mediamop.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.addFilter(shared_filter)
    file_handler.setFormatter(JsonLineFormatter())
    root.addHandler(file_handler)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True
