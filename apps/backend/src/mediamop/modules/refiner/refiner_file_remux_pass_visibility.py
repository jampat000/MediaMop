"""Compatibility alias for Refiner file remux pass visibility helpers."""

import sys

from mediamop.modules.refiner.file_remux_pass import visibility as _visibility

sys.modules[__name__] = _visibility
