"""Compatibility alias for the Refiner file remux pass path helpers."""

import sys

from mediamop.modules.refiner.file_remux_pass import paths as _paths

sys.modules[__name__] = _paths
