"""Property 20: risk filters and sort direction hold before pagination."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.services.risk import DISCLAIMER, RiskView, sort_risks

_LEVELS = ("低", "中", "高", "严重")
_ORDER = {level: index for index, level in enumerate(_LEVELS)}


@given(
    items=st.lists(
        st.tuples(st.sampled_from(_LEVELS), st.floats(min_value=0, max_value=100, allow_nan=False)),
        min_size=1,
        max_size=12,
    ),
    level=st.one_of(st.none(), st.sampled_from(_LEVELS)),
    descending=st.booleans(),
    page_size=st.integers(min_value=1, max_value=5),
)
@pytest.mark.property
def test_property_20_risk_filter_and_sort(
    items: list[tuple[str, float]],
    level: str | None,
    descending: bool,
    page_size: int,
) -> None:
    """Returned rows match the filter and neighboring scores follow the sort direction.

    **Feature: environmental-supervision-platform, Property 20: 风险筛选排序正确**
    **Property 20：风险筛选排序正确**
    **Validates: Requirements 8.8**
    """

    views = tuple(
        RiskView(
            compliance_key=f"k-{index}",
            risk_score=score,
            risk_level=item_level,
            legal_consequences="后果",
            recommended_actions=("建议",),
            penalty_estimate_text="无处罚",
            disclaimer=DISCLAIMER,
        )
        for index, (item_level, score) in enumerate(items)
    )
    ordered = sort_risks(views, level=level, descending=descending)
    assert all(level is None or item.risk_level == level for item in ordered)
    page = ordered[:page_size]
    assert page == ordered[:page_size]
    for left, right in zip(ordered, ordered[1:]):
        left_key = (_ORDER[left.risk_level], left.risk_score)
        right_key = (_ORDER[right.risk_level], right.risk_score)
        if descending:
            assert left_key >= right_key
        else:
            assert left_key <= right_key
