"""Property 13: legacy metrics match inverse-scaled NumPy error on valid cells."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.adapters.legacy.training import calculate_original_scale_metrics
from app.domain.dataframe_contracts import FEATURE_COLUMNS, ScalerArtifact


@given(
    steps=st.integers(min_value=1, max_value=3),
    mean=st.floats(min_value=0, max_value=3, allow_nan=False, allow_infinity=False),
    scale=st.floats(min_value=0.5, max_value=2, allow_nan=False, allow_infinity=False),
    data=st.data(),
)
@pytest.mark.property
def test_property_13_original_scale_metrics(
    steps: int,
    mean: float,
    scale: float,
    data: st.DataObject,
) -> None:
    """ResultsSaver metrics equal the NumPy reference and RMSE squared tracks MSE.

    **Feature: environmental-supervision-platform, Property 13: 原尺度指标正确**
    **Property 13：原尺度指标正确**
    **Validates: Requirements 5.10, 15.3, 16.3**
    """

    shape = (1, steps, 3)
    original = np.asarray(
        [
            [
                [
                    data.draw(st.floats(min_value=0, max_value=4, allow_nan=False, allow_infinity=False))
                    for _ in range(3)
                ]
                for _ in range(steps)
            ]
        ]
    )
    imputed = original + 0.25
    mask = np.ones(shape, dtype=bool)
    mask[0, 0, 0] = data.draw(st.booleans()) or True
    artifact = ScalerArtifact(
        feature_order=FEATURE_COLUMNS,
        mean=np.asarray([mean, mean, mean], dtype=float),
        scale=np.asarray([scale, scale, scale], dtype=float),
    )
    metrics = calculate_original_scale_metrics(original, imputed, mask, artifact)
    original_flat = original.reshape(-1, 3) * scale + mean
    imputed_flat = imputed.reshape(-1, 3) * scale + mean
    valid = mask.reshape(-1, 3)
    diff = (original_flat[valid] - imputed_flat[valid]).astype(float)
    mse = float(np.mean(diff**2))
    mae = float(np.mean(np.abs(diff)))
    assert metrics["MSE"] == pytest.approx(mse)
    assert metrics["MAE"] == pytest.approx(mae)
    assert metrics["RMSE"] ** 2 == pytest.approx(metrics["MSE"])
