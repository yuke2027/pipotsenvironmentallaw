"""Property 11: imputation fills only positions that were originally missing."""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.adapters.model_artifacts import apply_imputation


@given(
    values=st.lists(
        st.floats(min_value=0, max_value=20, allow_nan=False, allow_infinity=False),
        min_size=4,
        max_size=12,
    ),
    data=st.data(),
)
@pytest.mark.property
def test_property_11_imputation_keeps_observed_values(values: list[float], data: st.DataObject) -> None:
    """Observed cells stay unchanged and filled cells keep the original missing flag.

    **Feature: environmental-supervision-platform, Property 11: 插补只填缺失位置**
    **Property 11：插补只填缺失位置**
    **Validates: Requirements 5.3, 5.4**
    """

    observed = np.asarray(values, dtype=float)
    missing = np.asarray([data.draw(st.booleans()) for _ in values], dtype=bool)
    proposal = observed + np.asarray(
        [data.draw(st.floats(min_value=0, max_value=3, allow_nan=False, allow_infinity=False)) for _ in values]
    )
    filled, mask = apply_imputation(observed, missing, proposal)
    assert np.array_equal(mask, missing)
    assert np.array_equal(filled[~missing], observed[~missing])
    assert np.array_equal(filled[missing], proposal[missing])
