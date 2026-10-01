"""Property 14: model activation switches the pointer and handle together."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.services.models import ActivationState, activate_model

_STAGE = st.booleans()


@given(
    current=st.integers(min_value=1, max_value=20),
    candidate=st.integers(min_value=21, max_value=40),
    checksum=st.booleans(),
    manifest=st.booleans(),
    shape=st.booleans(),
    inference=st.booleans(),
)
@pytest.mark.property
def test_property_14_activation_is_atomic(
    current: int,
    candidate: int,
    checksum: bool,
    manifest: bool,
    shape: bool,
    inference: bool,
) -> None:
    """Both handles move only when every check passes; otherwise both stay put.

    **Feature: environmental-supervision-platform, Property 14: 模型切换原子性**
    **Property 14：模型切换原子性**
    **Validates: Requirements 5.9, 5.12**
    """

    state = ActivationState(db_id=current, memory_id=current)
    updated = activate_model(
        state,
        candidate,
        {"checksum": checksum, "manifest": manifest, "shape": shape, "inference": inference},
    )
    if checksum and manifest and shape and inference:
        assert updated.db_id == candidate
        assert updated.memory_id == candidate
    else:
        assert updated == state
