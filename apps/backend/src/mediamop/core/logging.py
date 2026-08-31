"""Process-wide logging configuration."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from traceback import format_exception

from mediamop.core.config import MediaMopSettings
from mediamop.platform.http.request_context import current_job_id, current_request_id
from mediamop.platform.metrics.service import record_log_record

_LOG_FILE_LOCK = threading.RLock()
_ACTIVE_FILE_HANDLER: LockedFileHandler | None = None
_ACTIVE_FILE_LEVEL = logging.INFO
_ACTIVE_FILE_FILTER: logging.Filter | None = None
logger = logging.getLogger(__name__)


class LockedFileHandler(logging.FileHandler):
    """File handler coordinated with retention replacement on Windows."""

    def emit(self, record: logging.LogRecord) -> None:
        with _LOG_FILE_LOCK:
            super().emit(record)


@contextlib.contextmanager
def log_file_lock():
    """Coordinate readers and retention rotation with active log writes."""

    with _LOG_FILE_LOCK:
        yield


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
    global _ACTIVE_FILE_HANDLER, _ACTIVE_FILE_LEVEL, _ACTIVE_FILE_FILTER
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)
        with contextlib.suppress(Exception):
            handler.close()

    shared_filter = MediaMopLogFilter()

    console = logging.StreamHandler()
    console.setLevel(level)
    console.addFilter(shared_filter)
    console.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(console)

    log_path = Path(settings.log_dir) / "mediamop.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = LockedFileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.addFilter(shared_filter)
    file_handler.setFormatter(JsonLineFormatter())
    root.addHandler(file_handler)
    _ACTIVE_FILE_HANDLER = file_handler
    _ACTIVE_FILE_LEVEL = level
    _ACTIVE_FILE_FILTER = shared_filter

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True


def prune_active_log_file(path: Path, *, keep_days: int) -> None:
    """Rewrite the active log while no writer or reader holds the file open.

    Windows does not allow replacing a file that still has an open handle.  The
    active handler is therefore flushed/closed before ``os.replace`` and recreated
    immediately afterwards, under the same lock used by ``LockedFileHandler.emit``.
    """

    global _ACTIVE_FILE_HANDLER
    path = path.resolve()
    if not path.is_file():
        return
    cutoff = datetime.now(UTC).timestamp() - max(1, int(keep_days)) * 86400
    tmp_name: str | None = None
    with _LOG_FILE_LOCK:
        root = logging.getLogger()
        current = _ACTIVE_FILE_HANDLER
        if current is not None and Path(current.baseFilename).resolve() == path:
            root.removeHandler(current)
            with contextlib.suppress(Exception):
                current.flush()
            with contextlib.suppress(Exception):
                current.close()
            _ACTIVE_FILE_HANDLER = None
        try:
            fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".prune", dir=str(path.parent))
            with path.open("r", encoding="utf-8") as source, os.fdopen(fd, "w", encoding="utf-8") as target:
                for raw in source:
                    try:
                        timestamp = json.loads(raw).get("timestamp")
                        at = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")).timestamp()
                    except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
                        continue
                    if at >= cutoff:
                        target.write(raw.rstrip("\n") + "\n")
            os.replace(tmp_name, path)
            tmp_name = None
        except OSError:
            logger.warning("Suite log prune skipped because the active log could not be rewritten.")
            if tmp_name:
                with contextlib.suppress(OSError):
                    Path(tmp_name).unlink()
        finally:
            if current is not None and Path(current.baseFilename).resolve() == path:
                reopened = LockedFileHandler(path, encoding="utf-8")
                reopened.setLevel(_ACTIVE_FILE_LEVEL)
                if _ACTIVE_FILE_FILTER is not None:
                    reopened.addFilter(_ACTIVE_FILE_FILTER)
                reopened.setFormatter(JsonLineFormatter())
                root.addHandler(reopened)
                _ACTIVE_FILE_HANDLER = reopened
