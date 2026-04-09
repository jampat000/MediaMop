"""Process-wide logging configuration."""

from __future__ import annotations

import logging

from mediamop.core.config import MediaMopSettings


def configure_logging(settings: MediaMopSettings) -> None:
    """Idempotent-friendly basic config for API and workers."""

    level_name = settings.log_level.upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
