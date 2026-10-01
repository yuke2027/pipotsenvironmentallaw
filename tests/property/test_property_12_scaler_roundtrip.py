"""Property 12: scaler transform and inverse transform round-trip finite matrices."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.adapters.model_artifacts import ArrayStandardizer, ArtifactError
from app.domain.dataframe_contracts import FEATURE_COLUMNS


@given(
    rows=st.integers(min_value=1, max_value=4),
    mean=st.lists(
        st.floats(min_value=-5, max_value=5, allow_nan=False, allow_infinity=False),
        min_size=3,
        max_size=3,
    ),
    scale=st.lists(
        st.floats(min_value=0.1, max_value=5, allow_nan=False, allow_infinity=False),
        min_size=3,
        max_size=3,
    ),
    data=st.data(),
)
@pytest.mark.property
def test_property_12_scaler_round_trip(
    rows: int,
    mean: list[float],
    scale: list[float],
    data: st.DataObject,
) -> None:
    """A matching scaler round-trips, and a wrong width or order is rejected.

    **Feature: environmental-supervision-platform, Property 12: 缩放制品往返**
    **Property 12：缩放制品往返**
    **Validates: Requirements 5.2, 5.6, 5.9**
    """

    matrix = np.asarray(
        [
            [
                data.draw(st.floats(min_value=0, max_value=10, allow_nan=False, allow_infinity=False))
                for _ in range(3)
            ]
            for _ in range(rows)
        ],
        dtype=float,
    )
    scaler = ArrayStandardizer(np.asarray(mean), np.asarray(scale), FEATURE_COLUMNS)
    restored = scaler.inverse_transform(scaler.transform(matrix))
    assert restored == pytest.approx(matrix)
    with pytest.raises(ArtifactError):
        scaler.transform(matrix[:, :2])
    with pytest.raises(ArtifactError):
        ArrayStandardizer(np.asarray(mean), np.asarray(scale), ("AQI", "PM10", "PM2.5"))
