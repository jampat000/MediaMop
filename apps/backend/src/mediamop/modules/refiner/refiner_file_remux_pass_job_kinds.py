"""Compatibility alias for the Refiner file remux pass job kinds."""

import sys

from mediamop.modules.refiner.file_remux_pass import job_kinds as _job_kinds

sys.modules[__name__] = _job_kinds
