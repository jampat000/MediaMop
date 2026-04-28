"""Compatibility alias for the Refiner file remux pass runner."""

import sys

from mediamop.modules.refiner.file_remux_pass import run as _run

sys.modules[__name__] = _run
