"""Guardrail: public ``arr_failed_import`` surface must not reintroduce refiner-prefixed names."""

from __future__ import annotations

import mediamop.modules.arr_failed_import as arr_failed_import


def test_arr_failed_import_all_exports_exclude_refiner_prefix() -> None:
    for name in arr_failed_import.__all__:
        assert "refiner" not in name.lower(), name
