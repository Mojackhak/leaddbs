"""Robust target-profile metric tests."""

import numpy as np
import pandas as pd

from ..analysis import (
    _pairwise_similarity,
    _robust_z,
    _safe_cosine,
    _safe_spearman,
)


def test_robust_z_is_not_shifted_by_one_extreme_value() -> None:
    values = np.asarray([1.0, 1.1, 0.9, 1.0, 20.0])
    scores = _robust_z(values)
    assert np.max(np.abs(scores[:4])) < 2.0
    assert scores[-1] > 100.0


def test_pairwise_spearman_preserves_subject_labels() -> None:
    matrix = pd.DataFrame(
        [[1.0, 2.0, 3.0], [2.0, 4.0, 6.0], [3.0, 2.0, 1.0]],
        index=["sub-a", "sub-b", "sub-c"],
        columns=["x", "y", "z"],
    )
    similarity = _pairwise_similarity(matrix, "spearman")
    assert list(similarity.index) == ["sub-a", "sub-b", "sub-c"]
    assert similarity.loc["sub-a", "sub-b"] == 1.0
    assert similarity.loc["sub-a", "sub-c"] == -1.0


def test_safe_metrics_report_constant_profiles_as_missing() -> None:
    constant = np.ones(3)
    varying = np.arange(3, dtype=float)
    assert np.isnan(_safe_spearman(constant, varying))
    assert np.isfinite(_safe_cosine(constant, varying))

