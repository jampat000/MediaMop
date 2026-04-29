"""Compatibility alias for Refiner file remux pass handlers."""

import sys

from mediamop.modules.refiner.file_remux_pass import handlers as _handlers

sys.modules[__name__] = _handlers
