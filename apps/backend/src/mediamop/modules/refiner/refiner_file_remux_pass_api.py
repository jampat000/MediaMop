"""Compatibility alias for the Refiner file remux pass API."""

import sys

from mediamop.modules.refiner.file_remux_pass import api as _api

sys.modules[__name__] = _api
