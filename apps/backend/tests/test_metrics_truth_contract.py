from __future__ import annotations

import pytest

from mediamop.platform.observability.metrics_truth import finalized_success_total, require_non_negative_metric_counts


def test_finalized_success_total_is_component_derived() -> None:
    assert finalized_success_total({"output_written": 2, "unchanged_copied": 3}) == 5


def test_metric_counts_reject_negative_values() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        require_non_negative_metric_counts({"files_processed": -1})
